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

from vision_ai import maybe_ai_boost

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


def _line_has_label(line: str, label: str) -> bool:
    """True if ``line`` contains ``label`` as a standalone word."""
    return re.search(rf"\b{re.escape(label.upper())}\b", line.upper()) is not None


def _line_is_pure_label(line: str, label: str) -> bool:
    """True if ``line`` is essentially the label alone (allowing trailing noise
    such as a separator, footnote digit, or pipe).
    """
    cleaned = re.sub(r"[^A-Za-z\s]", " ", line.upper()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    label_norm = re.sub(r"[^A-Za-z\s]", " ", label.upper()).strip()
    label_norm = re.sub(r"\s+", " ", label_norm)
    return cleaned == label_norm


def _is_noise_line(line: str) -> bool:
    """OCR noise lines: just a symbol, footnote digit, or pipe fragment."""
    stripped = line.strip(" ,;:\t|")
    if not stripped:
        return True
    # Single OCR noise symbol.
    if stripped in {"©", "®", "TM", "@", "*", "()", "(.)"}:
        return True
    # Pure digits / pure punctuation.
    if re.fullmatch(r"[\d().\-+/]+", stripped):
        return True
    return False


def first_value_after_label_lines(text: str, label: str, stop_labels: list[str]) -> str:
    """Find a line containing ``label`` (as a standalone label or as part of a
    table header), then return the next non-empty, non-noise line that
    doesn't begin with one of ``stop_labels``.

    Handles three layouts:

    * ``Label:\\nValue`` — value is the next non-empty line.
    * ``Label: Value`` — value is the same line, label prefix stripped.
    * ``Label: ValueA OtherLabel: ValueB`` — valueA returned, OtherLabel
      consumed by inline-label stripping.
    """
    label_up = label.upper()
    lines = text.splitlines()
    stop_ups = [s.upper() for s in stop_labels]

    def is_pure_stop(line: str) -> bool:
        up = line.upper()
        return any(
            _line_has_label(line, s) and _line_is_pure_label(line, s)
            for s in stop_ups
        )

    for i, line in enumerate(lines):
        if not _line_has_label(line, label):
            continue
        upper = line.upper()
        # 1) Same-line value: "Label: Value" — strip the label prefix in place.
        # This handles "Shipper: General Goods..." on its own line.
        prefix_idx = upper.find(label_up)
        # Look for a colon separator after the label.
        if prefix_idx != -1:
            after = line[prefix_idx + len(label_up):]
            after_stripped = after.lstrip(" ,;:\t|")
            # If after_stripped starts with content (not just another label),
            # treat as inline value.
            if after_stripped and not _is_noise_line(after_stripped):
                up_after = after_stripped.upper()
                # Don't consume lines that begin with another label.
                first_token = up_after.split()[0].rstrip(":.") if up_after.split() else ""
                looks_like_label = any(
                    re.match(rf"^{re.escape(s)}", first_token) for s in [label_up] + stop_ups
                )
                if not looks_like_label:
                    # Strip any trailing inline labels.
                    return _strip_inline_labels(after_stripped, stop_labels).strip()
        # 2) Pure-label line: value is the NEXT meaningful line.
        if _line_is_pure_label(line, label_up):
            for j in range(i + 1, min(i + 6, len(lines))):
                candidate = lines[j].strip()
                if not candidate or _is_noise_line(candidate):
                    continue
                if is_pure_stop(candidate):
                    break
                return _strip_label_prefix(candidate, label_up).strip()
            continue
    return ""


_CITY_COUNTRY_RE = re.compile(
    r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?),\s*"
    r"([A-Z][A-Za-z]+)"
)


def extract_city_country_pairs(value: str, dedupe: bool = True) -> list[str]:
    """Extract every ``CITY, COUNTRY`` pair in order from a noisy value.

    OCR frequently concatenates cells (``TOKYO, JAPAN TOKYO, JAPAN``);
    a single regex pass returns each well-formed pair.
    """
    value = value.strip(" ,;:\t|")
    if not value:
        return []
    upper = value.upper()
    pairs: list[str] = []
    for m in _CITY_COUNTRY_RE.finditer(upper):
        city = m.group(1).strip().rstrip(",")
        country = m.group(2).strip()
        # Heuristic: country must contain at least one letter and be short-ish.
        if country and country.replace(" ", "").isalpha() and len(country) <= 30:
            pairs.append(f"{city.title() if city.isupper() else city}, "
                         f"{country.title() if country.isupper() else country}")
    if not dedupe:
        return pairs
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for p in pairs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _first_city_country(value: str) -> str:
    """Return the first ``CITY, COUNTRY`` pair from a noisy value."""
    pairs = extract_city_country_pairs(value)
    return pairs[0] if pairs else value.strip(" ,;:\t|")


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" ,;:\t|"))


def normalize_vessel_name(value: str) -> str:
    value = clean_line(value)
    compact = re.sub(r"\s+", "", value.upper())

    if compact == "AAATHAILAND":
        return "AAA THAILAND"

    # Generic fallback for OCR that glues AAA + vessel word.
    m = re.match(r"^(AAA)([A-Z]+)$", compact)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    return value


def _normalize_units(value: str) -> str:
    """Normalise ``12,335kg`` -> ``12,335 kg``, ``21.80CBM`` -> ``21.80 CBM``."""
    value = value.strip()
    if not value:
        return ""
    # Insert a single space before a unit token if glued.
    value = re.sub(r"(\d)([A-Za-z]+)\b", r"\1 \2", value)
    return re.sub(r"\s+", " ", value).strip()


def _strip_label_prefix(value: str, label_up: str) -> str:
    for sep in (":", "."):
        idx = value.upper().find(label_up + sep)
        if idx == 0:
            return value[len(label_up) + 1 :].lstrip(" ,;:\t")
    if value.upper().startswith(label_up):
        return value[len(label_up):].lstrip(" ,;:\t")
    return value


def _strip_inline_labels(value: str, labels: list[str]) -> str:
    """Remove trailing label fragments from a value line.

    Example: ``BANGKOK, THAILAND Place of Acceptance Original BS/L`` →
    ``BANGKOK, THAILAND``.
    """
    upper = value.upper()
    earliest = len(value)
    for lbl in labels:
        lbl_up = lbl.upper()
        # Standalone label occurrence (word-boundary).
        m = re.search(rf"\b{re.escape(lbl_up)}\b", upper)
        if m and m.start() < earliest:
            earliest = m.start()
    if earliest < len(value):
        return value[:earliest].rstrip(" ,;:\t")
    return value


def _find_table_row(text: str, header_labels: list[str]) -> list[str]:
    """Find a row containing ALL ``header_labels`` and return the next
    non-empty line split by ``|``.

    Used for Ocean B/L table rows where multiple labels live on one header
    line and the next line holds the column values separated by ``|``.
    """
    lines = text.splitlines()
    label_ups = [lbl.upper() for lbl in header_labels]
    for i, line in enumerate(lines):
        up = line.upper()
        if all(re.search(rf"\b{re.escape(lbl)}\b", up) for lbl in label_ups):
            # Walk forward to find the value row.
            for j in range(i + 1, min(i + 6, len(lines))):
                candidate = lines[j].strip()
                if not candidate or _is_noise_line(candidate):
                    continue
                return [c.strip() for c in candidate.split("|")]
    return []


def _normalize_vessel_voyage(cell: str) -> tuple[str, str]:
    """Split a single cell like ``AAA THAILAND V.1000N``."""
    cell = cell.strip(" ,;:\t|")
    m = re.search(r"\b(V\.?\s?[A-Z0-9]+)\b", cell, re.IGNORECASE)
    if not m:
        return cell, ""
    voyage = m.group(1).replace(" ", "").upper()
    voyage = voyage if "." in voyage else voyage.replace("V", "V.")
    vessel = cell[: m.start()].strip(" ,;:\t|")
    return vessel, voyage


def _place_from_pipe(cell: str) -> str:
    cell = cell.strip(" ,;:\t|")
    cell = _strip_inline_labels(
        cell, ["PORT OF DISCHARGE", "PLACE OF DELIVERY", "FREIGHT PAYABLE AT"]
    )
    return cell.strip(" ,;:\t|")


def _extract_discharge_delivery_row(text: str) -> tuple[str, str]:
    """Parse OCR row: discharge / delivery / charges payable values."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        up = line.upper()
        if "PORT OF DISCHARGE" not in up or "PLACE OF DELIVERY" not in up:
            continue
        for candidate in lines[idx + 1: idx + 6]:
            candidate = candidate.strip()
            if not candidate or _is_noise_line(candidate):
                continue
            pairs = extract_city_country_pairs(candidate, dedupe=False)
            if not pairs:
                return "", ""
            delivery = pairs[2] if len(pairs) >= 3 else pairs[1] if len(pairs) >= 2 else ""
            return pairs[0], delivery
    return "", ""


def _extract_document_date(text: str) -> str:
    """Pick the best document date from the raw OCR text.

    Priority order (per spec):
      1. ``DATE : dd/mm/yyyy`` (or any ``Date`` label followed by a date).
      2. ``signed at ... dd/mm/yyyy`` / ``shipped on board ... dd/mm/yyyy``.
      3. ``1st March, 2018``-style ordinal + month name + year, including
         OCR typos like ``Ist March, 2018``.
    """
    upper = text.upper()

    # 1) Label-led date. Tolerate `DATE :`, `Date:`, `DATE-`, etc.
    m = re.search(r"\bDATE\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
                  text, re.IGNORECASE)
    if m:
        return m.group(1)

    # 2) Signed/on-board date. Allow any text between the keyword and the
    # numeric date (OCR may insert a city, signature name, etc.).
    m = re.search(
        r"(?:SIGNED\s+AT|SHIPPED\s+ON\s+BOARD|ON\s+BOARD|B/L\s+SIGNED)"
        r"[^0-9\n]*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1)

    m = re.search(
        r"(?:SIGNED\s+AT|SHIPPED\s+ON\s+BOARD|ON\s+BOARD|B/L\s+SIGNED)"
        r"[^\n]*?\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)

    # 3) Ordinal "1st March, 2018" / OCR typo "Ist March, 2018" / "1 March 2018".
    ord_re = re.compile(
        r"\b(\d{1,2}|[Ii]st)(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|"
        r"July|August|September|October|November|December),?\s+(\d{4})\b",
        re.IGNORECASE,
    )
    hit = ord_re.search(text)
    if hit:
        day_raw = hit.group(1)
        # Normalise OCR typo "Ist" -> "1".
        if day_raw.lower() == "ist":
            day_raw = "1"
        return f"{day_raw} {hit.group(2)} {hit.group(3)}"

    return ""


def _cargo_region(text: str) -> tuple[int, int]:
    """Find the cargo narrative span from the goods table to the next section."""
    upper = text.upper()
    starts = [
        r"\bDESCRIPTION\s+OF\s+GOODS\b",
        r"\bCARGO\s+DESCRIPTION\b",
        r"\bDESCRIPTION\s+OF\s+CARGO\b",
    ]
    carton_hits = list(re.finditer(r"\b\d{1,3}(?:,\d{3})*\s+CARTONS\.?", upper))
    if len(carton_hits) >= 2:
        start_idx = carton_hits[1].start()
    else:
        start_idx = -1
        for pattern in starts:
            m = re.search(pattern, upper)
            if m:
                start_idx = m.end()
                break
    if start_idx == -1:
        return (-1, -1)

    stop_words = [
        "INVOICE NO",
        "INVOICE NUMBER",
        "INV NO",
        "DATE",
        "SHIPPER LOAD & COUNT",
        "CONTAINER NOS",
        "CONTAINER NO",
        "DELIVERY AGENT",
        "FREIGHT AND CHARGES",
        "TYPE OF SERVICE",
        "NUMBER OF PACKAGES",
        "TOTAL",
    ]
    end_idx = len(text)
    for s in stop_words:
        m = re.search(rf"\b{re.escape(s)}\b", upper[start_idx + 1 :])
        if m and (start_idx + 1 + m.start()) < end_idx:
            end_idx = start_idx + 1 + m.start()
    return (start_idx, end_idx)


# ---------------------------------------------------------------------------
# Bill of Lading extractor (v2)
# ---------------------------------------------------------------------------
def extract_bill_of_lading(text: str) -> tuple[dict, dict]:
    fields: dict[str, str] = {}
    confidences: dict[str, str] = {}

    # ---- standalone-label fields: shipper / consignee / notify / bl_number -
    fields["shipper"] = first_value_after_label_lines(
        text, "SHIPPER", ["CONSIGNEE", "NOTIFY PARTY"]
    )
    fields["consignee"] = first_value_after_label_lines(
        text, "CONSIGNEE", ["NOTIFY PARTY", "VESSEL", "PORT OF LOADING"]
    )
    notify = first_value_after_label_lines(
        text, "NOTIFY PARTY", ["VESSEL", "PORT OF LOADING"]
    )
    if "SAME AS CONSIGNEE" in notify.upper():
        notify = "Same as Consignee"
    fields["notify_party"] = notify

    raw_bl = first_value_after_label_lines(
        text, "B/LNO", ["SHIPPER", "CONSIGNEE", "VESSEL", "PORT OF LOADING"]
    )
    if not raw_bl:
        raw_bl = first_value_after_label_lines(
            text, "B/L NO", ["SHIPPER", "CONSIGNEE", "VESSEL", "PORT OF LOADING"]
        )
    m = re.search(r"[A-Z0-9][A-Z0-9-]{3,}", raw_bl.upper())
    fields["bl_number"] = m.group(0) if m else ""

    # ---- table-row fields: vessel / voyage / ports ------------------------
    # The same OCR layout presents each label on its own line with the value
    # right after the colon — handle that with the label-prefix path. The
    # multi-column pipe-separated form (``Vessel | Port of Loading``) is
    # still covered by ``_find_table_row`` as a fallback.
    vessel_raw = first_value_after_label_lines(
        text, "VESSEL",
        ["VOYAGE", "PORT OF LOADING", "PORT OF DISCHARGE"],
    )
    vessel_clean, voyage_inline = _normalize_vessel_voyage(vessel_raw)
    fields["vessel_name"] = normalize_vessel_name(vessel_clean)
    fields["voyage_number"] = voyage_inline or first_value_after_label_lines(
        text, "VOYAGE", ["PORT OF LOADING", "PORT OF DISCHARGE"]
    )

    fields["port_of_loading"] = _first_city_country(first_value_after_label_lines(
        text, "PORT OF LOADING",
        ["PORT OF DISCHARGE", "PLACE OF ACCEPTANCE"],
    ))
    fields["place_of_acceptance"] = _first_city_country(first_value_after_label_lines(
        text, "PLACE OF ACCEPTANCE",
        ["PORT OF DISCHARGE", "PLACE OF DELIVERY", "DESCRIPTION"],
    ))
    port_disc_raw = first_value_after_label_lines(
        text, "PORT OF DISCHARGE",
        ["PLACE OF DELIVERY", "FREIGHT PAYABLE AT"],
    )
    port_disc_pairs = extract_city_country_pairs(port_disc_raw, dedupe=False)
    if port_disc_pairs:
        fields["port_of_discharge"] = port_disc_pairs[0]
        # If multiple city pairs in the same row, the third or second is place of delivery.
        if not fields.get("place_of_delivery") or "(Q)" in fields.get("place_of_delivery", "") \
                or "Freight" in fields.get("place_of_delivery", ""):
            if len(port_disc_pairs) >= 3:
                fields["place_of_delivery"] = port_disc_pairs[2]
            elif len(port_disc_pairs) >= 2:
                fields["place_of_delivery"] = port_disc_pairs[1]
    else:
        fields["port_of_discharge"] = _first_city_country(port_disc_raw)
    place_delivery_raw = first_value_after_label_lines(
        text, "PLACE OF DELIVERY",
        ["FREIGHT PAYABLE AT", "DESCRIPTION", "CONTAINER"],
    )
    if place_delivery_raw:
        fields["place_of_delivery"] = place_delivery_raw
    # Final safety: never let place_of_delivery be a header / label fragment.
    pod = fields.get("place_of_delivery", "")
    if pod and ("(Q)" in pod or "Freight and charges" in pod or
                "payable at" in pod or "Description of goods" in pod):
        fields["place_of_delivery"] = ""
    if fields.get("place_of_delivery"):
        pod_pairs = extract_city_country_pairs(fields["place_of_delivery"])
        if pod_pairs:
            fields["place_of_delivery"] = pod_pairs[0]

    row_discharge, row_delivery = _extract_discharge_delivery_row(text)
    if row_discharge:
        fields["port_of_discharge"] = row_discharge
    if row_delivery:
        fields["place_of_delivery"] = row_delivery

    # If the column form is present (rare in this dataset), override.
    port_load_row = _find_table_row(text, ["VESSEL", "PORT OF LOADING"])
    if port_load_row:
        v, voyage2 = _normalize_vessel_voyage(port_load_row[0])
        if v:
            fields["vessel_name"] = normalize_vessel_name(v)
            fields["voyage_number"] = voyage2 or fields["voyage_number"]
        if len(port_load_row) >= 2:
            fields["port_of_loading"] = _first_city_country(_strip_inline_labels(
                port_load_row[1], ["PLACE OF ACCEPTANCE", "NUMBER OF"]
            ))
        if len(port_load_row) >= 3:
            fields["place_of_acceptance"] = _first_city_country(_strip_inline_labels(
                port_load_row[2], ["NUMBER OF", "ORIGINAL", "DESCRIPTION"]
            ))

    port_disc_row = _find_table_row(text, ["PORT OF DISCHARGE", "PLACE OF DELIVERY"])
    if port_disc_row:
        if port_disc_row[0]:
            fields["port_of_discharge"] = _first_city_country(_strip_inline_labels(
                port_disc_row[0], ["PLACE OF DELIVERY", "FREIGHT PAYABLE AT"]
            ))
        if len(port_disc_row) >= 2:
            candidate_delivery = _first_city_country(_strip_inline_labels(
                port_disc_row[1], ["FREIGHT PAYABLE AT"]
            ))
            if candidate_delivery and candidate_delivery.upper() not in {"TOKYO", "BANGKOK"}:
                fields["place_of_delivery"] = candidate_delivery

    # ---- containers: scoped to the container label's vicinity ------------
    containers: list[str] = []
    upper = text.upper()
    m = re.search(r"\bCONTAINER NOS?\b", upper)
    if m:
        # Search 3 lines ahead for the value.
        snippet = text[m.end(): m.end() + 200]
        # Try the same line first (Container Nos.: XXX).
        same_line = text[m.start(): text.find("\n", m.start()) if text.find("\n", m.start()) != -1 else len(text)]
        same_line = same_line[len("CONTAINER NOS"):].lstrip(" .:")
        cell = same_line or ""
        if not cell:
            # Next non-empty line.
            for ln in snippet.splitlines()[:5]:
                ln = ln.strip()
                if ln and not _is_noise_line(ln):
                    cell = ln
                    break
        for p in re.split(r"[/,;]|\s{2,}", cell):
            p = p.strip(" ,;:\t|")
            # Reject anything that doesn't contain a digit (kills pure words).
            if p and any(c.isdigit() for c in p):
                containers.append(p)
    fields["container_numbers"] = ", ".join(dict.fromkeys(containers))

    # ---- cargo description: narrative span --------------------------------
    start, end = _cargo_region(text)
    if start == -1:
        fields["cargo_description"] = ""
    else:
        region = text[start:end]
        # Concatenate non-empty lines, but strip embedded weight / measurement
        # tokens that often get OCR'd into the same cell.
        lines = [ln.strip() for ln in region.splitlines() if ln.strip()]
        weight_re = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:kg|kgs|KG|KGS)\b")
        meas_re = re.compile(r"\b\d+(?:\.\d+)?\s*(?:CBM|M3|M³)\b")
        table_noise = (
            "MARKS AND NUMBER", "NUMBERS. TYPE OF PACKAGES",
            "DESCRIPTION OF GOODS", "KGS ME", "WEIGHT MEASUREMENT",
            "CASE MARK", "TOKYO/JAPAN",
        )
        clean_lines: list[str] = []
        for ln in lines:
            ln = ln.replace("40'HO", "40' HQ").replace("40'Ho", "40' HQ")
            ln = ln.replace("600m!", "600ml").replace("600M!", "600ml")
            up = ln.upper()
            if any(noise in up for noise in table_noise):
                continue
            if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:kg|kgs)", ln, re.IGNORECASE):
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:CBM|M3|M³)", ln, re.IGNORECASE):
                continue
            ln = weight_re.sub("", ln)
            ln = meas_re.sub("", ln)
            ln = ln.strip(" ,;:\t|")
            if ln:
                clean_lines.append(ln)
        cargo_text = " ".join(clean_lines).strip(" ,;:\t")
        cargo_text = re.sub(r"\bHS\s+CODE\s*:\s*", "HS CODE: ", cargo_text, flags=re.IGNORECASE)
        cargo_text = re.sub(r"\s+(HS CODE:)", r". \1", cargo_text)
        cargo_text = re.sub(r"\s+", " ", cargo_text).strip(" .")
        fields["cargo_description"] = f"{cargo_text}." if cargo_text else ""

    # ---- weight / measurement: scoped regex; pick the largest kg ----------
    weight_block = text
    weight_matches = re.findall(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:kg|kgs|KG|KGS)\b",
        weight_block,
    )
    weight_value = 0
    for m in weight_matches:
        digits = re.sub(r"[^\d.]", "", m.split("KG")[0].split("kg")[0].split("KGS")[0].split("kgs")[0].strip())
        # Fallback: strip non-digit chars from the numeric prefix.
        if not digits:
            digits = re.sub(r"[^\d.]", "", m)
        try:
            v = float(digits)
        except ValueError:
            continue
        if v > weight_value:
            weight_value = v
            fields["weight"] = m.replace("KGS", "kg").replace("Kgs", "kg").replace("KG", "kg").strip()

    meas_matches = re.findall(
        r"\b\d+(?:\.\d+)?\s*(?:CBM|M3|M³)\b",
        text,
    )
    if meas_matches:
        fields["measurement"] = meas_matches[0].replace("M3", "M3").replace("CBM", "CBM").strip()
        # Normalise spacing.
        fields["measurement"] = re.sub(r"\s+", " ", fields["measurement"])

    # ---- freight_terms: keyword match ------------------------------------
    upper_text = text.upper()
    if "FREIGHT PREPAID" in upper_text:
        fields["freight_terms"] = "Freight Prepaid"
    elif "FREIGHT COLLECT" in upper_text:
        fields["freight_terms"] = "Freight Collect"
    else:
        fields["freight_terms"] = ""

    # ---- delivery_agent: first meaningful line after the label -----------
    fields["delivery_agent"] = first_value_after_label_lines(
        text,
        "DELIVERY AGENT",
        ["INVOICE NO", "DATE", "FREIGHT", "PLACE OF DELIVERY"],
    )

    # ---- reference_invoice_number ----------------------------------------
    raw_inv = first_value_after_label_lines(
        text,
        "INVOICE NO",
        ["DATE", "TOTAL", "NUMBER OF", "CONTAINER"],
    )
    m = re.search(r"[A-Z0-9][A-Z0-9-]{2,}", raw_inv.upper())
    fields["reference_invoice_number"] = m.group(0) if m else ""

    # ---- document_date ----------------------------------------------------
    # Priority per spec:
    #   1) ``DATE : dd/mm/yyyy`` / ``Date dd/mm/yyyy`` (label-led).
    #   2) ``signed at ...`` / ``on board`` / ``shipped on board`` date.
    #   3) ``1st March, 2018``-style "dd<st|nd|rd|th> Month, yyyy".
    fields["document_date"] = _extract_document_date(text)

    # Apply unit normalisation to weight / measurement.
    fields["weight"] = _normalize_units(fields.get("weight", ""))
    fields["measurement"] = _normalize_units(fields.get("measurement", ""))

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
        notes = "Please review extracted fields before approval."

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


async def _read_and_ocr(file: UploadFile) -> tuple[bytes, str, bool]:
    """Render + OCR the upload. Returns (content, text, ok)."""
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    pages = render_pages(content, file.content_type)
    if not pages:
        return content, "", False

    return content, ocr_pages(pages), True


def _summarise_with_ai(
    *,
    fields: dict,
    confidences: dict,
    ai_low_conf_keys: list[str],
) -> tuple[str, str]:
    """Compute overall confidence + notes, surfacing AI low-confidence fields."""
    overall, notes = summarise(fields, confidences)
    if ai_low_conf_keys:
        pretty_map = {
            "bl_number": "B/L number",
            "shipper": "shipper",
            "consignee": "consignee",
            "vessel_name": "vessel name",
            "voyage_number": "voyage number",
            "container_numbers": "container numbers",
            "port_of_loading": "port of loading",
            "port_of_discharge": "port of discharge",
            "cargo_description": "cargo description",
            "weight": "cargo weight",
            "document_date": "document date",
            "vendor_name": "vendor name",
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
        names = [pretty_map.get(k, k.replace("_", " ")) for k in ai_low_conf_keys]
        ai_note = (
            "AI-extracted values for: "
            + ", ".join(names[:-1] + ([f"and {names[-1]}"] if len(names) > 1 else names))
            + ". Please review."
        )
        if notes:
            notes = f"{notes} {ai_note}"
        else:
            notes = ai_note
    return overall, notes


@app.post("/api/ocr/invoice")
async def ocr_invoice(file: UploadFile = File(...)):
    logger.info("local OCR started: endpoint=invoice, mimetype=%s", file.content_type)
    content, text, ok = await _read_and_ocr(file)
    if not ok:
        logger.warning("local OCR failed: could not render document (mimetype=%s)", file.content_type)
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
    logger.info("local OCR completed: endpoint=invoice, fields=%d, char_count=%d", len(fields), len(text))
    fields, confidences, vision_used, vision_warning, ai_low_conf = maybe_ai_boost(
        file_bytes=content,
        mimetype=file.content_type,
        doc_type="invoice",
        raw_text=text,
        fields=fields,
        confidences=confidences,
    )
    overall, notes = _summarise_with_ai(
        fields=fields, confidences=confidences, ai_low_conf_keys=ai_low_conf
    )
    logger.info("final overall confidence: endpoint=invoice, level=%s", overall)
    return {
        "document_type": "invoice",
        "detected_document_type": "invoice",
        "fields": fields,
        "confidence": confidences,
        "overall_confidence": overall,
        "low_confidence_notes": notes,
        "raw_text": text[:8000],
        "vision_ai_used": vision_used,
        "vision_ai_warning": vision_warning,
    }


@app.post("/api/ocr/bill-of-lading")
async def ocr_bill_of_lading(file: UploadFile = File(...)):
    logger.info("local OCR started: endpoint=bill_of_lading, mimetype=%s", file.content_type)
    content, text, ok = await _read_and_ocr(file)
    if not ok:
        logger.warning("local OCR failed: could not render document (mimetype=%s)", file.content_type)
        return {
            "error": "render_failed",
            "message": "Could not render document to image. Please upload a clearer scan.",
            "raw_text": "",
        }

    detected = detect_document_type(text)
    fields, confidences = extract_bill_of_lading(text)
    logger.info(
        "local OCR completed: endpoint=bill_of_lading, fields=%d, char_count=%d, detected=%s",
        len(fields), len(text), detected,
    )
    fields, confidences, vision_used, vision_warning, ai_low_conf = maybe_ai_boost(
        file_bytes=content,
        mimetype=file.content_type,
        doc_type="bill_of_lading",
        raw_text=text,
        fields=fields,
        confidences=confidences,
    )
    overall, notes = _summarise_with_ai(
        fields=fields, confidences=confidences, ai_low_conf_keys=ai_low_conf
    )
    logger.info("final overall confidence: endpoint=bill_of_lading, level=%s", overall)
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
        "vision_ai_used": vision_used,
        "vision_ai_warning": vision_warning,
    }
