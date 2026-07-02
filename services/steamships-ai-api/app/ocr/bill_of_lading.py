"""Bill of Lading OCR — placeholder extraction.

The original regex + vision-AI logic lives in
``services/document_ai_api/main.py``. This stub returns the schema-correct
shape with all fields null so the Odoo wizard can call the new endpoint
without crashing. Replace the body with the real extractor once the
``document-ai`` service is merged in.
"""

from __future__ import annotations

from .schemas import BillOfLadingResponse


def extract_bill_of_lading(filename: str, content: bytes, mimetype: str | None) -> BillOfLadingResponse:
    """Return an empty-but-shape-correct B/L payload.

    TODO(merge-ocr): wire the existing extractor from
    ``services/document_ai_api/main.py`` here. For now we return nulls with
    zero confidence so downstream callers can render a clean "pending" UI.
    """
    return BillOfLadingResponse()