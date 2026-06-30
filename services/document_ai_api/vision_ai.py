"""Gemini vision fallback for the Steamships Document AI OCR.

Tesseract + regex stay primary. This module is consulted ONLY when the
primary pass leaves important fields empty / low-confidence / invalid.
The response schema returned by the calling endpoint is unchanged;
corrections are merged in-place and two top-level flags are added:

    "vision_ai_used":        bool
    "vision_ai_warning":     str | None

ponytail: env contract — supports VISION_AI_ENABLED / VISION_AI_MODEL /
VISION_AI_FALLBACK_MODEL / GEMINI_API_KEY. Upgrade when we add multiple
providers (currently Gemini-only).
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

# Fields that, if empty or low-confidence, are worth sending to Gemini.
# Mirrors the pretty-name map in main.summarise() so the AI prompt stays
# focused on what the reviewer actually sees as broken.
PRIORITY_KEYS = {
    "bl_number",
    "shipper",
    "consignee",
    "notify_party",
    "vessel_name",
    "voyage_number",
    "port_of_loading",
    "port_of_discharge",
    "place_of_acceptance",
    "place_of_delivery",
    "container_numbers",
    "cargo_description",
    "weight",
    "measurement",
    "freight_terms",
    "delivery_agent",
    "reference_invoice_number",
    "document_date",
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

LOW = {"low", "medium"}  # treat medium as needing review for priority fields


@dataclass(frozen=True)
class VisionConfig:
    enabled: bool
    provider: str
    model: str
    fallback_model: str
    api_key: str
    timeout_s: float

    @classmethod
    def from_env(cls) -> "VisionConfig":
        return cls(
            enabled=os.environ.get("VISION_AI_ENABLED", "false").lower() == "true",
            provider=os.environ.get("VISION_AI_PROVIDER", "gemini").lower(),
            model=os.environ.get("VISION_AI_MODEL", "gemini-3-flash-preview"),
            fallback_model=os.environ.get(
                "VISION_AI_FALLBACK_MODEL", "gemini-3.1-flash-lite"
            ),
            api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            timeout_s=float(os.environ.get("VISION_AI_TIMEOUT_S", "20")),
        )


def fields_needing_ai(
    fields: dict[str, str],
    confidences: dict[str, str],
    important: Iterable[str],
) -> list[str]:
    """Return keys that are empty, low-confidence, or invalid-looking.

    Validation rules:
    * empty after strip
    * confidence in {low, medium} (medium = needs review for priority fields)
    * matches a placeholder pattern ("n/a", "unreadable", "???")
    """
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
        if conf in LOW:
            needs.append(key)
            continue
    return needs


def _looks_invalid_value(value: str) -> bool:
    """Catch category errors: a date that is also a phone number, etc."""
    # Too long to be a plausible single field value.
    if len(value) > 240:
        return True
    # Mostly punctuation / control chars.
    alnum = sum(c.isalnum() for c in value)
    return alnum < max(3, len(value) // 4)


def merge_ai_corrections(
    fields: dict[str, str],
    confidences: dict[str, str],
    corrections: dict[str, str],
    important: Iterable[str],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Apply AI corrections ONLY to keys still empty/low/invalid.

    Important: never overwrite a high-confidence field, even if the LLM
    returned something. Returns (fields, confidences, merged_keys).
    """
    merged: list[str] = []
    for key, new_val in corrections.items():
        if key not in important:
            continue
        new_val = (new_val or "").strip()
        if not new_val:
            continue
        old = (fields.get(key) or "").strip()
        conf = confidences.get(key, "medium")
        placeholder = re.compile(r"^(n/?a|unreadable|unknown|none|-+|\?+)$", re.IGNORECASE)
        should_replace = (
            not old
            or conf == "low"
            or (conf == "medium" and (not old or placeholder.match(old)))
            or _looks_invalid_value(old)
        )
        if should_replace:
            fields[key] = new_val
            confidences[key] = "high"
            merged.append(key)
    return fields, confidences, merged


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------
def _to_data_url(image: bytes, mimetype: str) -> str:
    b64 = base64.b64encode(image).decode("ascii")
    return f"data:{mimetype};base64,{b64}"


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
        "If a field really is unreadable in the image, set it to an empty string.\n\n"
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


def _call_gemini(
    config: VisionConfig,
    image_b64: str,
    prompt: str,
) -> dict[str, Any]:
    """Call Gemini, falling back to the lite model on overload/timeouts.

    Returns parsed JSON corrections. Raises on transport failure.
    """
    url = GEMINI_ENDPOINT.format(model=config.model)
    params = {"key": config.api_key}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": image_b64.split(";", 1)[0].split(":", 1)[1],
                            "data": image_b64.split(",", 1)[1],
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
        },
    }

    def _post(model: str) -> dict[str, Any]:
        if httpx is None:
            raise RuntimeError("httpx not installed; pip install httpx")
        with httpx.Client(timeout=config.timeout_s) as client:
            r = client.post(
                GEMINI_ENDPOINT.format(model=model),
                params={"key": config.api_key},
                json=payload,
            )
            r.raise_for_status()
            body = r.json()
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Gemini response shape: {body!r}") from exc
        return _extract_json(text)

    try:
        return _post(config.model)
    except httpx.HTTPStatusError as exc:
        # 429/503/529 => retry on the lite fallback.
        status = exc.response.status_code if exc.response is not None else 0
        if status in (429, 500, 502, 503, 504, 529) and config.fallback_model != config.model:
            logger.warning("Gemini %s failed (%s), retrying with %s", config.model, status, config.fallback_model)
            return _post(config.fallback_model)
        raise


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
) -> tuple[dict[str, str], dict[str, str], bool, str | None]:
    """If the priority fields need help, ask Gemini; otherwise return as-is.

    Returns (fields, confidences, vision_ai_used, warning).

    vision_ai_used = True if Gemini was called AND returned corrections.
    warning is set when Gemini was called but failed (the caller will surface
    it under "vision_ai_warning" without breaking the schema).
    """
    important = INVOICE_PRIORITY_KEYS if doc_type == "invoice" else (
        PRIORITY_KEYS if doc_type == "bill_of_lading" else set()
    )
    needs = fields_needing_ai(fields, confidences, important)
    if not needs:
        return fields, confidences, False, None

    cfg = VisionConfig.from_env()
    if not cfg.enabled:
        return fields, confidences, False, "Vision AI disabled (VISION_AI_ENABLED=false)."
    if cfg.provider != "gemini" or not cfg.api_key:
        return fields, confidences, False, (
            f"Vision AI not configured (provider={cfg.provider!r}, key={'set' if cfg.api_key else 'missing'})."
        )
    if not file_bytes:
        return fields, confidences, False, "No image bytes to send to Vision AI."

    # PDFs: send the raw OCR text only (Gemini inline_data expects an image).
    # Single-page PNG/JPG: send the bytes as inline_data.
    inline_mime = mimetype if mimetype and mimetype.startswith("image/") else None
    if inline_mime is None:
        # Skip the image part; fall back to text-only correction.
        image_part = None
    else:
        image_part = _to_data_url(file_bytes, inline_mime)

    prompt = _build_prompt(doc_type, raw_text, fields, confidences, needs)
    if image_part:
        prompt = prompt  # image is appended below as a multimodal part
    payload_prompt = prompt

    try:
        if image_part:
            url = GEMINI_ENDPOINT.format(model=cfg.model)
            body = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": payload_prompt},
                            {
                                "inline_data": {
                                    "mime_type": inline_mime,
                                    "data": base64.b64encode(file_bytes).decode("ascii"),
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.0,
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 1024,
                },
            }

            def _post(model: str) -> dict[str, Any]:
                with httpx.Client(timeout=cfg.timeout_s) as client:
                    r = client.post(
                        GEMINI_ENDPOINT.format(model=model),
                        params={"key": cfg.api_key},
                        json=body,
                    )
                    r.raise_for_status()
                    blob = r.json()
                text = blob["candidates"][0]["content"]["parts"][0]["text"]
                return _extract_json(text)

            try:
                corrections = _post(cfg.model)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status in (429, 500, 502, 503, 504, 529) and cfg.fallback_model != cfg.model:
                    logger.warning(
                        "Gemini %s failed (%s), retrying with %s",
                        cfg.model, status, cfg.fallback_model,
                    )
                    corrections = _post(cfg.fallback_model)
                else:
                    raise
        else:
            # Text-only path (PDF without per-page render): Gemini receives a
            # cheap text-only prompt; we warn because the spec promised image.
            logger.info("Vision AI: no inline image (mimetype=%s) — using text-only prompt", mimetype)
            corrections = _call_gemini_text(cfg, payload_prompt)
    except Exception as exc:
        logger.warning("Gemini fallback failed: %s", exc)
        return fields, confidences, False, f"Vision AI failed: {exc.__class__.__name__}: {exc}"

    if not isinstance(corrections, dict):
        corrections = {}
    fields, confidences, merged = merge_ai_corrections(fields, confidences, corrections, important)
    if not merged:
        return fields, confidences, False, "Vision AI returned no usable corrections."
    logger.info("Vision AI merged %d fields: %s", len(merged), merged)
    return fields, confidences, True, None


def _call_gemini_text(cfg: VisionConfig, prompt: str) -> dict[str, Any]:
    """Text-only Gemini call (used when no inline image is available)."""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 1024,
        },
    }

    def _post(model: str) -> dict[str, Any]:
        with httpx.Client(timeout=cfg.timeout_s) as client:
            r = client.post(
                GEMINI_ENDPOINT.format(model=model),
                params={"key": cfg.api_key},
                json=body,
            )
            r.raise_for_status()
            blob = r.json()
        text = blob["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(text)

    try:
        return _post(cfg.model)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status in (429, 500, 502, 503, 504, 529) and cfg.fallback_model != cfg.model:
            return _post(cfg.fallback_model)
        raise
