# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


STATE_SELECTION = [
    ("draft", "Draft"),
    ("pending_review", "Pending Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]


class SteamshipsBillLading(models.Model):
    _name = "steamships.bill.lading"
    _description = "Bill of Lading OCR Review"
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
    sequence_id = fields.Many2one(
        "ir.sequence",
        string="Sequence",
        copy=False,
    )

    # ------------------------------------------------------------------
    # Extracted B/L fields
    # ------------------------------------------------------------------
    bl_number = fields.Char(string="B/L Number", tracking=True)
    shipper = fields.Char(string="Shipper", tracking=True)
    consignee = fields.Char(string="Consignee", tracking=True)
    notify_party = fields.Char(string="Notify Party", tracking=True)
    vessel_name = fields.Char(string="Vessel Name", tracking=True)
    voyage_number = fields.Char(string="Voyage Number", tracking=True)
    container_numbers = fields.Char(
        string="Container Numbers",
        help="Comma-separated container numbers",
        tracking=True,
    )
    port_of_loading = fields.Char(string="Port of Loading", tracking=True)
    port_of_discharge = fields.Char(string="Port of Discharge", tracking=True)
    place_of_acceptance = fields.Char(
        string="Place of Acceptance",
        tracking=True,
    )
    place_of_delivery = fields.Char(
        string="Place of Delivery",
        tracking=True,
    )
    cargo_description = fields.Text(string="Cargo Description", tracking=True)
    weight = fields.Char(string="Weight (Gross)", tracking=True)
    measurement = fields.Char(string="Measurement", tracking=True)
    document_date = fields.Date(string="Document Date", tracking=True)
    freight_terms = fields.Char(string="Freight Terms", tracking=True)
    delivery_agent = fields.Char(string="Delivery Agent", tracking=True)
    reference_invoice_number = fields.Char(
        string="Reference Invoice Number",
        help=(
            "If the B/L cross-references a supplier invoice, capture it here. "
            "Never mix this up with the supplier invoice OCR record."
        ),
        tracking=True,
    )

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
            "steamships_document_ai.seq_steamships_bill_lading",
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
    def _post_state_change(self, body):
        self.ensure_one()
        self.message_post(body=body)

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
            rec._post_state_change(_("Bill of Lading approved by %s.") % self.env.user.name)

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
            rec._post_state_change(_("Bill of Lading rejected by %s.") % self.env.user.name)

    def action_reset_to_draft(self):
        for rec in self:
            rec.write(
                {
                    "state": "draft",
                    "reviewer_id": False,
                    "approved_date": False,
                }
            )
            rec._post_state_change(_("Status reset to Draft."))

    # ------------------------------------------------------------------
    # Hydration from OCR JSON
    # ------------------------------------------------------------------
    def populate_from_ocr(self, payload, file_content, filename, mimetype):
        """Create-or-update fields from an OCR JSON payload.

        Accepts BOTH the legacy doc-ai shape (``payload["fields"]["..."]``)
        AND the new unified steamships-ai-api shape where fields live at
        the top level (per the spec: ``bl_number``/``shipper``/.../``date``).
        The new shape wins when both are present.
        """
        self.ensure_one()
        payload = payload or {}
        fields_map = dict(payload.get("fields") or {})

        # New spec shape — top-level keys override nested "fields" for the
        # same name; ``date`` is the spec's name for the B/L document date.
        for key in (
            "bl_number", "shipper", "consignee", "notify_party",
            "vessel_name", "voyage_number", "container_numbers",
            "port_of_loading", "port_of_discharge", "place_of_acceptance",
            "place_of_delivery", "cargo_description", "weight", "measurement",
            "freight_terms", "delivery_agent", "reference_invoice_number",
        ):
            if key in payload and payload[key] not in (None, "", []):
                fields_map[key] = payload[key]
        if "document_date" not in fields_map and payload.get("date"):
            fields_map["document_date"] = payload["date"]

        values = {
            "bl_number": fields_map.get("bl_number"),
            "shipper": fields_map.get("shipper"),
            "consignee": fields_map.get("consignee"),
            "notify_party": fields_map.get("notify_party"),
            "vessel_name": fields_map.get("vessel_name"),
            "voyage_number": fields_map.get("voyage_number"),
            "container_numbers": fields_map.get("container_numbers"),
            "port_of_loading": fields_map.get("port_of_loading"),
            "port_of_discharge": fields_map.get("port_of_discharge"),
            "place_of_acceptance": fields_map.get("place_of_acceptance"),
            "place_of_delivery": fields_map.get("place_of_delivery"),
            "cargo_description": fields_map.get("cargo_description"),
            "weight": fields_map.get("weight"),
            "measurement": fields_map.get("measurement"),
            "document_date": _parse_date(fields_map.get("document_date")),
            "freight_terms": fields_map.get("freight_terms"),
            "delivery_agent": fields_map.get("delivery_agent"),
            "reference_invoice_number": fields_map.get("reference_invoice_number"),
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
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    # Strip ordinal suffixes like ``1st``, ``2nd``, ``3rd``, ``4th``.
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %B, %Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except (ValueError, TypeError):
            continue
    return False
