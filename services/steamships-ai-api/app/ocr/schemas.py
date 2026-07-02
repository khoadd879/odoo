"""Pydantic schemas for the OCR endpoints.

The shapes match the requirements document (sections 3, 10) so the existing
Odoo `steamships_document_ai` wizard continues to receive a predictable
response.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class BillOfLadingResponse(BaseModel):
    bl_number: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    vessel_name: Optional[str] = None
    voyage_number: Optional[str] = None
    container_numbers: List[str] = Field(default_factory=list)
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    cargo_description: Optional[str] = None
    weight: Optional[str] = None
    date: Optional[str] = None
    confidence: Dict[str, float] = Field(default_factory=dict)
    detected_document_type: str = "bill_of_lading"


class InvoiceResponse(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[str] = None
    currency: Optional[str] = None
    line_items: List[dict] = Field(default_factory=list)
    confidence: Dict[str, float] = Field(default_factory=dict)
    detected_document_type: str = "invoice"
    status: str = "not_implemented"