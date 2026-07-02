# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models


STATE_SELECTION = [
    ("draft", "Draft"),
    ("pending_review", "Pending Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


class SteamshipsInvoiceOcr(models.Model):
    _name = "steamships.invoice.ocr"
    _description = "Supplier Invoice OCR Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )

    # ------------------------------------------------------------------
    # Extracted invoice fields
    # ------------------------------------------------------------------
    vendor_name = fields.Char(string="Vendor", tracking=True)
    invoice_number = fields.Char(string="Invoice Number", tracking=True)
    invoice_date = fields.Date(string="Invoice Date", tracking=True)
    due_date = fields.Date(string="Due Date", tracking=True)
    currency = fields.Char(string="Currency", tracking=True, size=8)
    subtotal_amount = fields.Char(string="Subtotal", tracking=True)
    tax_amount = fields.Char(string="Tax Amount", tracking=True)
    total_amount = fields.Char(string="Total Amount", tracking=True)
    payment_terms = fields.Char(string="Payment Terms", tracking=True)

    # ------------------------------------------------------------------
    # Workflow / review
    # ------------------------------------------------------------------
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    overall_confidence = fields.Char(string="Overall Confidence", readonly=True)
    low_confidence_notes = fields.Text(
        string="Low-Confidence Notes",
        readonly=True,
        help="Fields the OCR service flagged for human review.",
    )
    reviewer_id = fields.Many2one(
        "res.users",
        string="Reviewer",
        readonly=True,
        copy=False,
    )
    approved_date = fields.Datetime(string="Approved Date", readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Source document
    # ------------------------------------------------------------------
    original_filename = fields.Char(string="Original Filename")
    original_file = fields.Binary(string="Original File", attachment=True)
    original_mimetype = fields.Char(string="MIME Type")
    raw_ocr_text = fields.Text(string="Raw OCR Text", readonly=True)
    raw_json = fields.Text(string="Raw OCR JSON", readonly=True)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    is_review_open = fields.Boolean(
        compute="_compute_review_open",
        string="Review Open",
    )

    @api.depends("state")
    def _compute_review_open(self):
        for rec in self:
            rec.is_review_open = rec.state in ("draft", "pending_review")

    # ------------------------------------------------------------------
    # Sequence
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env.ref(
            "steamships_document_ai.seq_steamships_invoice_ocr",
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New") and seq:
                vals["name"] = seq.next_by_id()
        records = super().create(vals_list)
        for rec in records:
            if rec.raw_ocr_text:
                rec.message_post(
                    body=_(
                        "OCR extraction completed. Please review low-confidence "
                        "fields before approval."
                    ),
                )
        return records

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def action_approve(self):
        for rec in self:
            if rec.state == "approved":
                continue
            rec.write(
                {
                    "state": "approved",
                    "reviewer_id": self.env.user.id,
                    "approved_date": fields.Datetime.now(),
                }
            )
            rec.message_post(body=_("Invoice approved by %s.") % self.env.user.name)

    def action_reject(self):
        for rec in self:
            if rec.state == "rejected":
                continue
            rec.write(
                {
                    "state": "rejected",
                    "reviewer_id": self.env.user.id,
                }
            )
            rec.message_post(body=_("Invoice rejected by %s.") % self.env.user.name)

    def action_reset_to_draft(self):
        for rec in self:
            rec.write(
                {
                    "state": "draft",
                    "reviewer_id": False,
                    "approved_date": False,
                }
            )
            rec.message_post(body=_("Status reset to Draft."))

    # ------------------------------------------------------------------
    # Hydration from OCR JSON
    # ------------------------------------------------------------------
    def populate_from_ocr(self, payload, file_content, filename, mimetype):
        """Create-or-update fields from an OCR JSON payload.

        Accepts BOTH the legacy doc-ai shape (``payload["fields"]["..."]``)
        AND the new unified steamships-ai-api shape where fields live at
        the top level.
        """
        self.ensure_one()
        payload = payload or {}
        fields_map = dict(payload.get("fields") or {})

        # New spec shape — top-level keys win when present.
        for key in (
            "vendor_name", "invoice_number", "invoice_date", "due_date",
            "currency", "subtotal_amount", "tax_amount", "total_amount",
            "payment_terms",
        ):
            if key in payload and payload[key] not in (None, "", []):
                fields_map[key] = payload[key]

        values = {
            "vendor_name": fields_map.get("vendor_name"),
            "invoice_number": fields_map.get("invoice_number"),
            "invoice_date": _parse_date(fields_map.get("invoice_date")),
            "due_date": _parse_date(fields_map.get("due_date")),
            "currency": fields_map.get("currency"),
            "subtotal_amount": fields_map.get("subtotal_amount"),
            "tax_amount": fields_map.get("tax_amount"),
            "total_amount": fields_map.get("total_amount"),
            "payment_terms": fields_map.get("payment_terms"),
            "raw_ocr_text": payload.get("raw_text") or "",
            "raw_json": json.dumps(payload, indent=2, default=str),
            "overall_confidence": payload.get("overall_confidence"),
            "low_confidence_notes": payload.get("low_confidence_notes"),
            "original_filename": filename,
            "original_file": file_content,
            "original_mimetype": mimetype,
            "state": "pending_review",
        }
        self.write(values)
        self.message_post(
            body=_("Document extracted by OCR and is ready for human review."),
        )


def _parse_date(value):
    """Best-effort YYYY-MM-DD parse. Returns False when empty/invalid."""
    if not value:
        return False
    import datetime as _dt
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return _dt.datetime.strptime(text, fmt).date()
        except (ValueError, TypeError):
            continue
    return False
