from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BillOfLading(models.Model):
    _name = 'bill.of.lading'
    _description = 'Bill of Lading (AI-extracted, human-reviewed)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='B/L Number', required=True, tracking=True)
    shipper = fields.Char(string='Shipper', tracking=True)
    consignee = fields.Char(string='Consignee', tracking=True)
    notify_party = fields.Char(string='Notify Party')
    vessel_name = fields.Char(string='Vessel', tracking=True)
    voyage_number = fields.Char(string='Voyage No.')
    container_numbers = fields.Text(string='Container No(s)')
    port_of_loading = fields.Char(string='Port of Loading')
    port_of_discharge = fields.Char(string='Port of Discharge')
    cargo_description = fields.Text(string='Cargo Description')
    gross_weight_kg = fields.Float(string='Gross Weight (kg)')
    bl_date = fields.Date(string='B/L Date')

    # AI extraction metadata
    confidence_score = fields.Float(string='Overall Confidence', default=0.0,
        help="0.0–1.0 from AI extraction. <0.7 means human must review carefully.")
    low_confidence_fields = fields.Char(string='Low-confidence fields',
        help="Comma-separated field names flagged by AI for re-check.")
    source_scan_filename = fields.Char(string='Source scan filename')
    source_attachment_id = fields.Many2one('ir.attachment', string='Source scan')

    # Workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending_review', required=True, tracking=True)

    reviewer_id = fields.Many2one('res.users', string='Reviewer')
    reviewed_date = fields.Datetime(string='Reviewed at')
    review_notes = fields.Text(string='Review notes')

    # Demo helper: synthetic confidence for sample_bl_scans.xml
    @api.model
    def _set_low_confidence_fields(self, vals):
        """Move fields with confidence < 0.7 to low_confidence_fields list."""
        # Implementation in Task 2 (extraction logic).
        return vals

    def action_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'reviewer_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
            rec.message_post(body='B/L approved.', subtype_xmlid='mail.mt_note')

    def action_reject(self):
        for rec in self:
            if not rec.review_notes or not rec.review_notes.strip():
                raise UserError(_('Rejection reason (review notes) is required.'))
            rec.write({
                'state': 'rejected',
                'reviewer_id': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
            rec.message_post(
                body=_('B/L rejected. Reason: %s') % rec.review_notes,
                subtype_xmlid='mail.mt_note')

    def action_reset_to_review(self):
        for rec in self:
            rec.write({'state': 'pending_review'})

    def action_upload_scan_wizard(self):
        """No-op wrapper. The actual upload is triggered client-side via JS
        (static/src/js/bl_upload.js) which posts to /steamships/bl/extract.
        This method exists so the form button has a callable action.
        """
        for rec in self:
            rec.message_post(
                body=_('B/L upload triggered. Use the file picker to attach a scan image.'),
                subtype_xmlid='mail.mt_note')
        return True
