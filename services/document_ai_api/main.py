"""Steamships Document AI OCR — Day 5.

FastAPI service that accepts a PDF/PNG/JPG, runs Tesseract OCR, then
extracts structured fields for two document types:

* ``invoice``
* ``bill_of_lading``

The shape of the JSON returned to Odoo is fixed (see ``/api/ocr/invoice``
and ``/api/ocr/bill-of-lading``); only the extraction logic inside
``extractor.py`` will change in Day 6 when we swap Tesseract + regex for
a vision LLM. Keep the schema stable.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Iterable

import pytesseract
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

logger = logging.getLogger("document_ai")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Steamships Document AI", version="1.0.0")


# ---------------------------------------------------------------------------
# Document rendering
# ---------------------------------------------------------------------------
def render_pages(content: bytes, mimetype: str | None) -> list[Image.Image]:
    """Yield PIL images for the upload (PDF pages or single image)."""
    pages: list[Image.Image] = []
    is_pdf = (mimetype == "application/pdf") or content.startswith(b"%PDF")

    if is_pdf:
        # Lazy import keeps PNG-only cold start cheap.
        from pdf2image import convert_from_bytes

        try:
            pages = convert_from_bytes(content, dpi=200)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("pdf2image failed: %s", exc)
            return []
    else:
        try:
            img = Image.open(io.BytesIO(content))
            img.load()
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            pages.append(img)
        except Exception as exc:
            logger.warning("Pillow failed to open image: %s", exc)
            return []

    return pages


def ocr_pages(pages: Iterable[Image.Image]) -> str:
    """Run Tesseract per page; concatenate the text."""
    chunks: list[str] = []
    for idx, page in enumerate(pages):
        try:
            text = pytesseract.image_to_string(page)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("tesseract failed on page %s: %s", idx, exc)
            continue
        if text:
            chunks.append(text)
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


@dataclass
class FieldResult:
    value: str
    confidence: str

    def is_low(self) -> bool:
        return self.confidence == CONFIDENCE_LOW


# Heuristic: if a value has fewer than 2 alphanumerics OR is shorter than 3
# chars OR matches a known placeholder ("n/a", "unreadable", ...), treat it
# as low confidence. Otherwise normalise to medium unless the value looks
# rich (>=6 chars with a mix of alpha+numeric OR uppercase tokens).
def score(value: str | None) -> str:
    if value is None:
        return CONFIDENCE_LOW
    text = value.strip()
    if not text:
        return CONFIDENCE_LOW
    low_pattern = re.compile(r"^(n/?a|unreadable|unknown|none|-+|\?+)$", re.IGNORECASE)
    if low_pattern.match(text):
        return CONFIDENCE_LOW
    alpha = sum(c.isalpha() for c in text)
    digit = sum(c.isdigit() for c in text)
    if alpha + digit < 3:
        return CONFIDENCE_LOW
    if alpha >= 6 and (digit >= 2 or any(t.isupper() for t in text.split())):
        return CONFIDENCE_HIGH
    return CONFIDENCE_MEDIUM


# ---------------------------------------------------------------------------
# Regex extractors
# ---------------------------------------------------------------------------
NUMBER_RE = re.compile(r"\b(\d{6,})\b")  # 6+ consecutive digits
DATE_RES = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
]
PORT_RES = [
    re.compile(r"PORT\s+OF\s+LOADING[:\s]+([A-Z][A-Za-z\s]+)", re.IGNORECASE),
    re.compile(r"FROM[:\s]+([A-Z][A-Za-z\s]+)", re.IGNORECASE),
    re.compile(r"LOADING[:\s]+([A-Z][A-Za-z\s]{2,})", re.IGNORECASE),
]
PORT_DISCHARGE_RES = [
    re.compile(r"PORT\s+OF\s+DISCHARGE[:\s]+([A-Z][A-Za-z\s]+)", re.IGNORECASE),
    re.compile(r"DISCHARGE[:\s]+([A-Z][A-Za-z\s]{2,})", re.IGNORECASE),
    re.compile(r"TO[:\s]+([A-Z][A-Za-z\s]+)", re.IGNORECASE),
]
CURRENCY_RES = [
    re.compile(r"\b(USD|PHP|AUD|NZD|EUR|GBP|JPY|SGD|CNY|HKD|INR)\b"),
]


def first_match(text: str, regexes: list[re.Pattern], group: int = 1) -> str:
    for rgx in regexes:
        m = rgx.search(text)
        if m:
            return m.group(group).strip(" ,;:\n\t")
    return ""


# ---------------------------------------------------------------------------
# Bill of Lading extractor
# ---------------------------------------------------------------------------
# Order matters: defines stop-words when carving blocks from the text.
BOL_LABEL_ORDER = [
    ("bl_number", ["B/LNO", "B/L NO", "B/L NUMBER", "BILL OF LADING NO"]),
    ("shipper", ["SHIPPER", "CONSIGNOR"]),
    ("consignee", ["CONSIGNEE"]),
    ("notify_party", ["NOTIFY PARTY", "NOTIFY"]),
    ("vessel_name", ["VESSEL"]),
    ("voyage_number", ["VOYAGE", "VOYAGE NO", "VOYAGE NUMBER"]),
    ("port_of_loading", ["PORT OF LOADING"]),
    ("port_of_discharge", ["PORT OF DISCHARGE"]),
    ("place_of_acceptance", ["PLACE OF ACCEPTANCE"]),
    ("place_of_delivery", ["PLACE OF DELIVERY", "FINAL DELIVERY"]),
    ("container_numbers", ["CONTAINER NOS", "CONTAINER NO"]),
    ("cargo_description", ["DESCRIPTION OF GOODS", "CARGO DESCRIPTION"]),
    ("weight", ["GROSS WEIGHT", "NET WEIGHT", "WEIGHT"]),
    ("measurement", ["MEASUREMENT", "MEAS."]),
    ("freight_terms", ["FREIGHT PREPAID", "FREIGHT COLLECT", "FREIGHT TERMS"]),
    ("delivery_agent", ["DELIVERY AGENT", "DELIVERING AGENT", "CARRIER"]),
    ("reference_invoice_number", ["INVOICE NO", "INVOICE NUMBER", "INV NO", "INV #"]),
    ("document_date", ["DATE"]),
]


def _label_positions(text: str) -> list[tuple[int, str]]:
    """Return ``(start_char, uppercased_label)`` for every label occurrence.

    Word-boundary match so ``NOTIFY`` inside ``NOTIFY PARTY`` is reported as
    the longer match. Longer labels win so partial overlaps are avoided.
    """
    upper = text.upper()
    candidates = sorted({lbl for _, group in BOL_LABEL_ORDER for lbl in group},
                        key=len, reverse=True)
    hits: list[tuple[int, str]] = []
    for lbl in candidates:
        for m in re.finditer(rf"\b{re.escape(lbl)}\b", upper):
            hits.append((m.start(), lbl))
    hits.sort(key=lambda x: x[0])
    return hits


def _split_label_inline(line: str, label: str) -> str:
    """Strip ``LABEL:`` / ``LABEL.`` / ``LABEL`` prefix from a single line."""
    up = line.upper()
    label_up = label.upper()
    for sep in (":", "."):
        idx = up.find(label_up + sep)
        if idx != -1:
            return line[idx + len(label) + 1 :].strip(" ,;:\t")
    idx = up.find(label_up)
    if idx == 0:
        return line[len(label):].strip(" ,;:\t")
    return line.strip(" ,;:\t")


def _extract_vessel_voyage(line: str) -> tuple[str, str]:
    """Handle the common B/L line ``AAA THAILAND V.1000N`` (no separate label)."""
    text = line.strip(" ,;:\t")
    m = re.search(r"\b(V\.?\s?[A-Z0-9]+)\b", text, re.IGNORECASE)
    if not m:
        return text, ""
    voyage = m.group(1).replace(" ", "").upper()
    voyage = voyage if "." in voyage else voyage.replace("V", "V.")
    vessel = text[: m.start()].strip(" ,;:\t")
    return vessel, voyage


def extract_bill_of_lading(text: str) -> tuple[dict, dict]:
    fields: dict[str, str] = {}
    confidences: dict[str, str] = {}

    positions = _label_positions(text)
    starts: dict[str, int] = {}
    label_at: dict[str, str] = {}
    for key, group in BOL_LABEL_ORDER:
        group_upper = {g.upper() for g in group}
        for pos_char, pos_lbl in positions:
            if pos_lbl in group_upper and key not in starts:
                starts[key] = pos_char
                label_at[key] = pos_lbl
                break
    ordered_keys = [k for k, _ in BOL_LABEL_ORDER if k in starts]
    blocks: dict[str, tuple[int, int]] = {}
    for i, key in enumerate(ordered_keys):
        end = (
            starts[ordered_keys[i + 1]]
            if i + 1 < len(ordered_keys)
            else len(text)
        )
        blocks[key] = (starts[key], end)

    # Helper: get the FIRST non-label line of a block, then trim label prefix.
    def block_first_line(key: str) -> str:
        if key not in blocks:
            return ""
        start, end = blocks[key]
        head = text[start:end]
        first_line = next((ln for ln in head.splitlines() if ln.strip()), "")
        return _split_label_inline(first_line, label_at.get(key, ""))

    # Helper: get all non-label lines of a block (skips the label-line itself).
    def block_body_lines(key: str) -> list[str]:
        if key not in blocks:
            return []
        start, end = blocks[key]
        lbl_up = label_at.get(key, "").upper()
        body: list[str] = []
        for ln in text[start:end].splitlines():
            s = ln.strip()
            if not s:
                continue
            up = s.upper()
            # Skip the bare-label line.
            if up.startswith(lbl_up):
                continue
            # Also skip a line that IS just the label (e.g. ``Container Nos.``).
            if up.rstrip(":.").strip() == lbl_up.rstrip(":.").strip():
                continue
            body.append(s)
        return body

    # ---- bl_number ---------------------------------------------------------
    raw_bl = block_first_line("bl_number")
    m = re.search(r"[A-Z0-9][A-Z0-9-]{3,}", raw_bl)
    fields["bl_number"] = m.group(0) if m else ""

    # ---- shipper / consignee / notify_party --------------------------------
    fields["shipper"] = block_first_line("shipper")
    fields["consignee"] = block_first_line("consignee")
    notify = block_first_line("notify_party")
    if "SAME AS CONSIGNEE" in notify.upper():
        notify = "Same as Consignee"
    fields["notify_party"] = notify

    # ---- vessel / voyage ---------------------------------------------------
    # Vessel label often appears in the form ``Vessel: AAA THAILAND``
    # followed by a separate ``Voyage: V.1000N`` label on its own line.
    vessel_line = block_first_line("vessel_name")
    if vessel_line:
        # If the vessel line happens to also contain ``V.NNN``, split it.
        if re.search(r"\bV\.?\s?[A-Z0-9]+\b", vessel_line):
            vessel, voyage_inline = _extract_vessel_voyage(vessel_line)
            fields["vessel_name"] = vessel
            fields["voyage_number"] = voyage_inline or block_first_line("voyage_number")
        else:
            fields["vessel_name"] = vessel_line
            fields["voyage_number"] = block_first_line("voyage_number")
    else:
        fields["vessel_name"] = ""
        fields["voyage_number"] = block_first_line("voyage_number")

    # ---- ports -------------------------------------------------------------
    fields["port_of_loading"] = block_first_line("port_of_loading")
    fields["port_of_discharge"] = block_first_line("port_of_discharge")
    fields["place_of_acceptance"] = block_first_line("place_of_acceptance")
    fields["place_of_delivery"] = block_first_line("place_of_delivery")

    # ---- containers --------------------------------------------------------
    # Pull ONLY from the container block. ``GGE10001`` lives in the
    # reference_invoice_number block, so scoped search kills cross-pollution.
    # Containers appear right after the label on the same line, so we strip
    # the label inline rather than dropping the line.
    container_block_text = ""
    if "container_numbers" in blocks:
        start, end = blocks["container_numbers"]
        container_block_text = text[start:end]
    # First try to grab the value part from the label line.
    lbl_up = label_at.get("container_numbers", "").upper()
    cell = ""
    if lbl_up:
        for ln in container_block_text.splitlines():
            if not ln.strip():
                continue
            up = ln.upper()
            if up.startswith(lbl_up):
                cell = ln[len(lbl_up):].lstrip(" :.;\t")
                break
    if not cell:
        # Fall back to the first non-label line.
        for ln in container_block_text.splitlines():
            s = ln.strip()
            if not s or s.upper().startswith(lbl_up):
                continue
            cell = s
            break
    containers: list[str] = []
    for p in re.split(r"[/,;]|\s{2,}", cell):
        p = p.strip(" ,;:\t")
        if p and any(c.isdigit() for c in p):
            containers.append(p)
    fields["container_numbers"] = ", ".join(dict.fromkeys(containers))

    # ---- cargo_description -------------------------------------------------
    # The body of the description block often spans several lines and may
    # include the next label's line (e.g. ``Gross Weight: 12,335 kg``) when
    # the original document packed two rows into one OCR line.
    cargo_body = block_body_lines("cargo_description")
    cargo_clean: list[str] = []
    weight_re = re.compile(r"\b\d[\d.,]*\s?(?:kg|kgs|KGS|Kg)\b")
    meas_re = re.compile(r"\b\d[\d.,]*\s?(?:CBM|cbm|M3|m3)\b")
    for ln in cargo_body:
        if weight_re.search(ln) or meas_re.search(ln):
            # Strip embedded weight/measurement tokens that snuck into cargo.
            ln = weight_re.sub("", ln)
            ln = meas_re.sub("", ln).strip(" ,;:\t")
        if ln:
            cargo_clean.append(ln)
    fields["cargo_description"] = " ".join(cargo_clean).strip(" ,;:\t")

    # ---- weight / measurement ---------------------------------------------
    weight_block = text[blocks["weight"][0] : blocks["weight"][1]] if "weight" in blocks else ""
    m = re.search(r"\b([0-9][0-9.,]*\s?(?:kg|kgs|KGS|Kg))\b", weight_block)
    fields["weight"] = m.group(1) if m else ""

    meas_block = text[blocks["measurement"][0] : blocks["measurement"][1]] if "measurement" in blocks else ""
    m = re.search(r"\b([0-9][0-9.,]*\s?(?:CBM|cbm|M3|m3))\b", meas_block)
    fields["measurement"] = m.group(1) if m else ""

    # ---- freight_terms -----------------------------------------------------
    freight_block = text[blocks["freight_terms"][0] : blocks["freight_terms"][1]] if "freight_terms" in blocks else ""
    upper_freight = freight_block.upper()
    if "FREIGHT PREPAID" in upper_freight:
        fields["freight_terms"] = "Freight Prepaid"
    elif "FREIGHT COLLECT" in upper_freight:
        fields["freight_terms"] = "Freight Collect"
    else:
        fields["freight_terms"] = ""

    # ---- delivery_agent ----------------------------------------------------
    fields["delivery_agent"] = block_first_line("delivery_agent")

    # ---- reference_invoice_number ------------------------------------------
    inv_block_first = block_first_line("reference_invoice_number")
    m = re.search(r"[A-Z0-9][A-Z0-9-]{2,}", inv_block_first.upper())
    fields["reference_invoice_number"] = m.group(0) if m else ""

    # ---- document_date -----------------------------------------------------
    date_block = text[blocks["document_date"][0] : blocks["document_date"][1]] if "document_date" in blocks else ""
    date_candidates: list[str] = []
    for rgx in DATE_RES:
        for m in rgx.finditer(date_block):
            date_candidates.append(m.group(1))
    fields["document_date"] = date_candidates[0] if date_candidates else block_first_line("document_date")

    # Confidence per field.
    for key, value in fields.items():
        confidences[key] = score(value)

    return fields, confidences


def _first_header_line(text: str) -> str:
    """Return the first all-alpha, non-trivial line in the text.

    Serves as a fallback vendor/shipper guess when no explicit label is
    matched by ``_slice_after_label``.
    """
    for raw in text.splitlines():
        line = raw.strip(" ,;:\t")
        if not line:
            continue
        if len(line) < 3:
            continue
        # Require mostly letters; reject pure-numeric / invoice-number lines.
        alpha = sum(c.isalpha() for c in line)
        digit = sum(c.isdigit() for c in line)
        if alpha < 3 or alpha <= digit:
            continue
        # Reject obvious label-only fragments.
        if line.upper().startswith(("INVOICE", "DATE", "DUE", "BILL TO")):
            continue
        return line[:80]
    return ""


def _slice_after_label(text: str, labels: list[str], max_chars: int = 120) -> str:
    upper = text.upper()
    for label in labels:
        idx = upper.find(label.upper() + ":")
        if idx == -1:
            idx = upper.find(label.upper())
            if idx == -1:
                continue
            start = idx + len(label)
        else:
            start = idx + len(label) + 1
        # Take the chunk until double newline or 4 lines, whichever first.
        tail = text[start : start + max_chars]
        tail = tail.split("\n\n", 1)[0]
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        if not lines:
            continue
        return " ".join(lines)[:max_chars].strip(" ,;:")
    return ""


# ---------------------------------------------------------------------------
# Invoice extractor
# ---------------------------------------------------------------------------
def extract_invoice(text: str) -> tuple[dict, dict]:
    fields: dict[str, str] = {}
    confidences: dict[str, str] = {}

    # Vendor label — fall back to first non-numeric header line.
    vendor = _slice_after_label(text, ["VENDOR", "FROM", "SELLER"], max_chars=120)
    if not vendor:
        vendor = _first_header_line(text)
    fields["vendor_name"] = vendor

    fields["invoice_number"] = _slice_after_label(
        text,
        ["INVOICE NO", "INVOICE #", "INVOICE NUMBER", "INV NO", "INV #"],
        max_chars=40,
    )
    fields["invoice_date"] = first_match(text, DATE_RES)
    fields["due_date"] = _slice_after_label(text, ["DUE DATE", "DUE"], max_chars=40)

    fields["currency"] = first_match(text, CURRENCY_RES)
    fields["subtotal_amount"] = _slice_after_label(
        text, ["SUBTOTAL", "SUB-TOTAL", "SUB TOTAL"], max_chars=40
    )
    fields["tax_amount"] = _slice_after_label(
        text, ["TAX", "VAT", "GST"], max_chars=40
    )
    fields["total_amount"] = _slice_after_label(
        text,
        ["TOTAL DUE", "AMOUNT DUE", "GRAND TOTAL", "TOTAL"],
        max_chars=40,
    )
    fields["payment_terms"] = _slice_after_label(
        text,
        ["PAYMENT TERMS", "TERMS"],
        max_chars=80,
    )

    for key, value in fields.items():
        confidences[key] = score(value)

    return fields, confidences


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def summarise(fields: dict, confidences: dict) -> tuple[str, str]:
    if not confidences:
        return CONFIDENCE_MEDIUM, ""

    counter = {CONFIDENCE_HIGH: 0, CONFIDENCE_MEDIUM: 0, CONFIDENCE_LOW: 0}
    for level in confidences.values():
        counter[level] = counter.get(level, 0) + 1

    total = sum(counter.values()) or 1
    if counter[CONFIDENCE_LOW] / total >= 0.4:
        overall = CONFIDENCE_LOW
    elif counter[CONFIDENCE_HIGH] / total >= 0.5:
        overall = CONFIDENCE_HIGH
    else:
        overall = CONFIDENCE_MEDIUM

    low_keys = [k for k, level in confidences.items() if level == CONFIDENCE_LOW]
    if low_keys:
        pretty = {
            "vendor_name": "vendor name",
            "shipper": "shipper",
            "consignee": "consignee",
            "bl_number": "B/L number",
            "vessel_name": "vessel name",
            "voyage_number": "voyage number",
            "container_numbers": "container numbers",
            "port_of_loading": "port of loading",
            "port_of_discharge": "port of discharge",
            "place_of_acceptance": "place of acceptance",
            "place_of_delivery": "place of delivery",
            "cargo_description": "cargo description",
            "weight": "cargo weight",
            "measurement": "measurement",
            "document_date": "document date",
            "freight_terms": "freight terms",
            "delivery_agent": "delivery agent",
            "reference_invoice_number": "reference invoice number",
            "invoice_number": "invoice number",
            "invoice_date": "invoice date",
            "due_date": "due date",
            "currency": "currency",
            "subtotal_amount": "subtotal",
            "tax_amount": "tax amount",
            "total_amount": "total amount",
            "payment_terms": "payment terms",
            "notify_party": "notify party",
        }
        names = [pretty.get(k, k.replace("_", " ")) for k in low_keys]
        notes = (
            "Please check "
            + ", ".join(names[:-1] + ([f"and {names[-1]}"] if len(names) > 1 else names))
            + "."
        )
    else:
        notes = ""

    return overall, notes


# ---------------------------------------------------------------------------
# Document type detection
# ---------------------------------------------------------------------------
BOL_KEYWORDS = [
    "OCEAN BILL OF LADING",
    "BILL OF LADING",
    "B/LNO",
    "B/L NO",
    "B/L NUMBER",
    "PORT OF LOADING",
    "PORT OF DISCHARGE",
    "VESSEL",
    "CONTAINER NOS",
    "CONTAINER NO",
    "SHIPPER",
    "CONSIGNEE",
    "NOTIFY PARTY",
]

INVOICE_KEYWORDS = [
    "INVOICE",
    "TAX INVOICE",
    "SUPPLIER INVOICE",
    "INVOICE NO",
    "INVOICE NUMBER",
    "TOTAL AMOUNT",
    "SUBTOTAL",
    "TAX AMOUNT",
    "DUE DATE",
    "PAYMENT TERMS",
]


def detect_document_type(raw_text: str) -> str:
    """Score keyword presence to choose between ``bill_of_lading`` / ``invoice`` / ``unknown``.

    A document classified as ``bill_of_lading`` only needs >=3 B/L keywords
    AND a B/L score >= invoice score. The hard override "OCEAN BILL OF
    LADING" is handled implicitly because it contributes 1 to bol_score.
    """
    text = (raw_text or "").upper()

    bol_score = sum(1 for kw in BOL_KEYWORDS if kw in text)
    invoice_score = sum(1 for kw in INVOICE_KEYWORDS if kw in text)

    if bol_score >= 3 and bol_score >= invoice_score:
        return "bill_of_lading"
    if invoice_score >= 3:
        return "invoice"
    return "unknown"


# ---------------------------------------------------------------------------
# FastAPI endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "steamships-document-ai"}


async def _read_and_ocr(file: UploadFile) -> tuple[str, bool]:
    """Render + OCR the upload. Returns (text, ok)."""
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    pages = render_pages(content, file.content_type)
    if not pages:
        return "", False

    return ocr_pages(pages), True


@app.post("/api/ocr/invoice")
async def ocr_invoice(file: UploadFile = File(...)):
    text, ok = await _read_and_ocr(file)
    if not ok:
        return {
            "error": "render_failed",
            "message": "Could not render document to image. Please upload a clearer scan.",
            "raw_text": "",
        }

    detected = detect_document_type(text)
    if detected == "bill_of_lading":
        # Hard guard — refuse to coerce a B/L into an invoice JSON.
        return {
            "error": "document_type_mismatch",
            "detected_document_type": "bill_of_lading",
            "message": (
                "This document looks like a Bill of Lading, not a supplier "
                "invoice. Please upload it as Bill of Lading."
            ),
        }
    if detected == "unknown":
        return {
            "error": "document_type_unknown",
            "detected_document_type": "unknown",
            "message": (
                "Could not detect whether this is an invoice or Bill of "
                "Lading. Please upload a clearer scan."
            ),
        }

    fields, confidences = extract_invoice(text)
    overall, notes = summarise(fields, confidences)
    return {
        "document_type": "invoice",
        "detected_document_type": "invoice",
        "fields": fields,
        "confidence": confidences,
        "overall_confidence": overall,
        "low_confidence_notes": notes,
        "raw_text": text[:8000],
    }


@app.post("/api/ocr/bill-of-lading")
async def ocr_bill_of_lading(file: UploadFile = File(...)):
    text, ok = await _read_and_ocr(file)
    if not ok:
        return {
            "error": "render_failed",
            "message": "Could not render document to image. Please upload a clearer scan.",
            "raw_text": "",
        }

    detected = detect_document_type(text)
    fields, confidences = extract_bill_of_lading(text)
    overall, notes = summarise(fields, confidences)
    # We always return the B/L schema. ``detected_document_type`` surfaces
    # the classifier's call so the wizard can reject a pure-invoice doc.
    return {
        "document_type": "bill_of_lading",
        "detected_document_type": detected or "bill_of_lading",
        "fields": fields,
        "confidence": confidences,
        "overall_confidence": overall,
        "low_confidence_notes": notes,
        "raw_text": text[:8000],
    }
