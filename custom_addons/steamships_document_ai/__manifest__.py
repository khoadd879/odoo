# -*- coding: utf-8 -*-
{
    "name": "Steamships Document AI OCR",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "OCR and AI document extraction for invoices and Bills of Lading",
    "description": """
Day 5 — Steamships Document AI OCR
==================================

Custom OCR review flow for Odoo 19 Community:

* Upload wizard accepts a PDF/image (invoice or Bill of Lading).
* Wizard calls the standalone FastAPI OCR service
  (DOCUMENT_AI_URL env var, default ``http://document-ai:9100``).
* OCR returns structured JSON fields + confidence scores.
* Odoo creates a record in either ``steamships.invoice.ocr`` or
  ``steamships.bill.lading`` with state ``pending_review``.
* Reviewer checks low-confidence fields, then Approves / Rejects.

No Enterprise, Studio, or ``iap_extract`` dependency.
""",
    "author": "Steamships Prototype Team",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/bill_lading_views.xml",
        "views/invoice_ocr_views.xml",
        "views/upload_wizard_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
