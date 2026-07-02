"""Supplier-invoice OCR — placeholder.

Like ``bill_of_lading.py``, this is a stub that returns the schema with
``status="not_implemented"``. The real extractor will be merged in once the
OCR service consolidation lands.
"""

from __future__ import annotations

from .schemas import InvoiceResponse


def extract_invoice(filename: str, content: bytes, mimetype: str | None) -> InvoiceResponse:
    """Return a ``not_implemented`` invoice payload."""
    return InvoiceResponse()