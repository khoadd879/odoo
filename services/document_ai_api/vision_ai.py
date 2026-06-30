"""Gemini vision fallback for the Steamships Document AI OCR.

Tesseract + regex stay primary. This module is consulted ONLY when the
primary pass leaves important fields empty / low-confidence / invalid.
The response schema returned by the calling endpoint is unchanged;
corrections are merged in-place and two top-level flags are added:

    "vision_ai_used":        bool
    "vision_ai_warning":     str | None

ponytail: env contract — supports VISION_AI_ENABLED / VISION_AI_MODEL /
VISION_AI_FALLBACK_MODEL / VISION_AI_ENABLE_BOL / VISION_AI_ENABLE_INVOICE /
GEMINI_API_KEY. Upgrade when we add multiple providers (currently Gemini-only).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

try:
    import httpx  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - allow offline unit tests
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger("document_ai.vision")

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Spec-defined Bill of Lading priority set. Keep this list frozen; the
# spec dict is the source of truth.
PRIORITY_KEYS = {
    "bl_number",
    "shipper",
    "consignee",
    "vessel_name",
    "voyage_number",
    "container_numbers",
    "port_of_loading",
    "port_of_discharge",
    "cargo_description",
    "weight",
    "document_date",
}

# Non-priority B/L fields still useful for general cleanup; not in the spec
# list but kept so the AI can fix obvious misses (notify party, ports etc.)
EXTRA_BOL_KEYS = {
    "notify_party",
    "place_of_acceptance",
    "place_of_delivery",
    "measurement",
    "freight_terms",
    "delivery_agent",
    "reference_invoice_number",
}

INVOICE_PRIORITY_KEYS = {
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal_amount",
    "tax_amount",
    "total_amount",
    "payment_terms",
}

# Treat low and medium as candidates for AI rescue on priority fields only.
LOW_FOR_AI = {"low", "medium"}


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


@dataclass(frozen=True)
class VisionConfig:
    enabled: bool
    provider: str
    model: str
    fallback_model: str
    api_key: str
    timeout_s: float
    enable_bol: bool
    enable_invoice: bool

    @classmethod
    def from_env(cls) -> "VisionConfig":
        return cls(
            enabled=_truthy("VISION_AI_ENABLED", "false"),
            provider=os.environ.get("VISION_AI_PROVIDER", "gemini").lower(),
            model=os.environ.get("VISION_AI_MODEL", "gemini-3-flash-preview"),
            fallback_model=os.environ.get(
                "VISION_AI_FALLBACK_MODEL", "gemini-3.1-flash-lite"
            ),
            api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            timeout_s=float(os.environ.get("VISION_AI_TIMEOUT_S", "90")),
            enable_bol=_truthy("VISION_AI_ENABLE_BOL", "true"),
            enable_invoice=_truthy("VISION_AI_ENABLE_INVOICE", "false"),
        )


def fields_needing_ai(
    fields: dict[str, str],
    confidences: dict[str, str],
    important: Iterable[str],
) -> list[str]:
    """Return keys that are empty, low-confidence, invalid, or placeholder."""
    placeholder = re.compile(r"^(n/?a|unreadable|unknown|none|-+|\?+)$", re.IGNORECASE)
    needs: list[str] = []
    for key in important:
        value = (fields.get(key) or "").strip()
        conf = confidences.get(key, "medium")
        if not value:
            needs.append(key)
            continue
        if placeholder.match(value):
            needs.append(key)
            continue
        if conf in LOW_FOR_AI:
            needs.append(key)
            continue
        if _looks_invalid_value(value):
            needs.append(key)
            continue
    return needs


def _looks_invalid_value(value: str) -> bool:
    """Catch category errors: a date that is also a phone number, etc."""
    if len(value) > 240:
        return True
    alnum = sum(c.isalnum() for c in value)
    return alnum < max(3, len(value) // 4)


def merge_ai_corrections(
    fields: dict[str, str],
    confidences: dict[str, str],
    corrections: dict[str, Any],
    important: Iterable[str],
) -> tuple[dict[str, str], dict[str, str], list[str], list[str]]:
    """Apply AI corrections ONLY to keys still empty/low/invalid.

    The corrections payload is flexible:
      {"field": "value"}                                  -> assume medium AI conf
      {"field": {"value": "...", "confidence": "high"}}    -> use provided conf

    Returns: (fields, confidences, merged_keys, low_confidence_keys).

    Spec rule: never overwrite a high-confidence local value; if Gemini
    returns low confidence, write the value but flag it for human review.
    """
    placeholder = re.compile(r"^(n/?a|unreadable|unknown|none|-+|\?+)$", re.IGNORECASE)
    important_set = set(important)
    merged: list[str] = []
    ai_low_conf: list[str] = []

    for key, raw in corrections.items():
        if key not in important_set:
            continue
        if isinstance(raw, dict):
            new_val = (raw.get("value") or "").strip()
            ai_conf = (raw.get("confidence") or "medium").lower()
        else:
            new_val = (str(raw) or "").strip()
            ai_conf = "medium"
        if not new_val:
            continue
        old = (fields.get(key) or "").strip()
        conf = confidences.get(key, "medium")
        should_replace = (
            not old
            or conf == "low"
            or (conf == "medium" and (not old or placeholder.match(old)))
            or _looks_invalid_value(old)
        )
        if not should_replace:
            logger.info("Skipped AI overwrite on high-confidence field '%s'", key)
            continue
        fields[key] = new_val
        # Confidence promotion rules: spec says AI high/medium -> use, AI low ->
        # write but flag for review.
        if ai_conf == "high":
            confidences[key] = "high"
        elif ai_conf == "low":
            confidences[key] = "low"
            ai_low_conf.append(key)
        else:
            confidences[key] = "medium"
        merged.append(key)

    return fields, confidences, merged, ai_low_conf


# ---------------------------------------------------------------------------
# Gemini call helpers
# ---------------------------------------------------------------------------
def _build_prompt(
    doc_type: str,
    raw_text: str,
    fields: dict[str, str],
    confidences: dict[str, str],
    needs: list[str],
) -> str:
    return (
        "You are a document-extraction assistant.\n"
        f"Document type: {doc_type}.\n"
        "You are given:\n"
        "  (1) the original document as an image attachment,\n"
        "  (2) the raw OCR text the local pipeline produced,\n"
        "  (3) the fields the local pipeline already extracted,\n"
        "  (4) the field names that the local pipeline could not get right.\n\n"
        "Your task: re-inspect the attached image and return ONLY a JSON object "
        "whose keys are exactly the field names in (4) and whose values are the "
        "corrected strings. Do not invent fields that were not requested. "
        "If a field really is unreadable in the image, set it to an empty string. "
        "Prefer returning strings; you may add a sibling key {\"value\":...,\"confidence\":\"high|medium|low\"} "
        "if you want to flag your own confidence.\n\n"
        "Respond with JSON only — no markdown fences, no commentary.\n\n"
        f"Raw OCR text (first 4000 chars):\n{raw_text[:4000]}\n\n"
        f"Current fields:\n{json.dumps(fields, ensure_ascii=False)}\n\n"
        f"Current confidences:\n{json.dumps(confidences, ensure_ascii=False)}\n\n"
        f"Fields to correct:\n{json.dumps(needs, ensure_ascii=False)}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Gemini sometimes wraps JSON in ```json ...``` fences; strip them."""
    text = text.strip()
    fence = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _post_gemini(model: str, api_key: str, body: dict, timeout_s: float):
    if httpx is None:
        raise RuntimeError("httpx not installed; pip install httpx")
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(
            GEMINI_ENDPOINT.format(model=model),
            params={"key": api_key},
            json=body,
        )
        r.raise_for_status()
        return r.json()


def _extract_text(blob: dict) -> str:
    try:
        return blob["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response shape: {blob!r}") from exc


def _build_body(prompt: str, inline_image: tuple[bytes, str] | None) -> dict:
    parts: list[dict] = [{"text": prompt}]
    if inline_image is not None:
        blob, mimetype = inline_image
        parts.append(
            {
                "inline_data": {
                    "mime_type": mimetype,
                    "data": base64.b64encode(blob).decode("ascii"),
                }
            }
        )
    return {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
        },
    }


def _call_gemini(
    cfg: VisionConfig, body: dict, attempt_model: str | None = None
) -> tuple[dict[str, Any], str]:
    """Call Gemini, then possibly retry once on the lite fallback model.

    Returns (parsed_corrections, model_used). Raises on transport failure.
    """
    primary = attempt_model or cfg.model

    def _try(model: str) -> dict[str, Any]:
        blob = _post_gemini(model, cfg.api_key, body, cfg.timeout_s)
        return _extract_json(_extract_text(blob))

    try:
        return _try(primary), primary
    except Exception as exc:  # httpx.HTTPStatusError or similar
        status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
        if status in (429, 500, 502, 503, 504, 529) and cfg.fallback_model and cfg.fallback_model != primary:
            logger.warning(
                "Gemini %s failed (status=%s). Retrying with fallback %s.",
                primary, status, cfg.fallback_model,
            )
            blob = _post_gemini(cfg.fallback_model, cfg.api_key, body, cfg.timeout_s)
            return _extract_json(_extract_text(blob)), cfg.fallback_model
        raise


def _ai_disabled_reason(cfg: VisionConfig, doc_type: str) -> str | None:
    """Human-readable skip-reason; None means AI is armed for this doc type."""
    if not cfg.enabled:
        return "Vision AI disabled (VISION_AI_ENABLED=false)."
    if cfg.provider != "gemini":
        return f"Vision AI provider '{cfg.provider}' not supported (only 'gemini' today)."
    if not cfg.api_key:
        return "GEMINI_API_KEY is not configured."
    if doc_type == "bill_of_lading" and not cfg.enable_bol:
        return "Vision AI disabled for Bill of Lading (VISION_AI_ENABLE_BOL=false)."
    if doc_type == "invoice" and not cfg.enable_invoice:
        return "Vision AI disabled for invoices (VISION_AI_ENABLE_INVOICE=false)."
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def maybe_ai_boost(
    *,
    file_bytes: bytes,
    mimetype: str | None,
    doc_type: str,
    raw_text: str,
    fields: dict[str, str],
    confidences: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], bool, str | None, list[str]]:
    """If priority fields need help, ask Gemini; otherwise return as-is.

    Returns (fields, confidences, vision_ai_used, warning, ai_low_conf_keys).

    * ``vision_ai_used`` — True iff Gemini was called AND produced corrections.
    * ``warning`` — set when Gemini was called but failed.
    * ``ai_low_conf_keys`` — fields where AI returned low confidence; caller
       bubbles them into ``low_confidence_notes`` for the reviewer.
    """
    # Build the priority set per spec: BOL spec list +/- invoice list.
    if doc_type == "bill_of_lading":
        important = PRIORITY_KEYS | EXTRA_BOL_KEYS
    elif doc_type == "invoice":
        important = INVOICE_PRIORITY_KEYS
    else:
        important = set()

    needs = fields_needing_ai(fields, confidences, important)
    if not needs:
        logger.info("AI fallback skipped: all priority fields already validated (doc_type=%s)", doc_type)
        return fields, confidences, False, None, []

    cfg = VisionConfig.from_env()
    skip_reason = _ai_disabled_reason(cfg, doc_type)
    if skip_reason:
        logger.info("AI fallback skipped: %s", skip_reason)
        return fields, confidences, False, skip_reason, []

    if not file_bytes:
        logger.warning("AI fallback skipped: no file bytes available to send.")
        return fields, confidences, False, "No document bytes available for Vision AI.", []

    # Image path: send inline_data when mimetype is image/*. Text-only otherwise.
    inline: tuple[bytes, str] | None = None
    if mimetype and mimetype.startswith("image/"):
        inline = (file_bytes, mimetype)

    prompt = _build_prompt(doc_type, raw_text, fields, confidences, needs)
    body = _build_body(prompt, inline)

    try:
        logger.info(
            "AI fallback triggered: doc_type=%s, model=%s, fields=%d (%s)",
            doc_type, cfg.model, len(needs), ",".join(sorted(needs)),
        )
        corrections, model_used = _call_gemini(cfg, body)
    except Exception as exc:
        # Spec wording: "AI fallback failed; using local OCR result."
        logger.warning("AI fallback failed: %s: %s", exc.__class__.__name__, exc)
        return fields, confidences, False, "AI fallback failed; using local OCR result.", []

    if not isinstance(corrections, dict) or not corrections:
        logger.info("AI fallback returned no usable corrections (model=%s)", model_used)
        return fields, confidences, False, "Vision AI returned no usable corrections.", []

    fields, confidences, merged, ai_low_conf = merge_ai_corrections(
        fields, confidences, corrections, important
    )
    if not merged:
        logger.info("AI fallback: model %s returned keys, but none replaced weak fields.", model_used)
        return fields, confidences, False, "Vision AI returned no usable corrections.", ai_low_conf

    logger.info(
        "AI fallback succeeded: model=%s, merged=%d, low_conf=%d (%s)",
        model_used, len(merged), len(ai_low_conf), ",".join(ai_low_conf) or "none",
    )
    return fields, confidences, True, None, ai_low_conf
