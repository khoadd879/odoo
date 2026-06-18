from odoo import _, models, fields, api


class CrmLeadSteamshipsOnboarding(models.Model):
    _name = 'crm.lead.steamships.onboarding'
    _description = 'Steamships Customer Onboarding & KYC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    lead_id = fields.Many2one('crm.lead', required=True, ondelete='cascade', string='CRM Lead')
    partner_id = fields.Many2one('res.partner', related='lead_id.partner_id', readonly=True)
    company_id = fields.Many2one('res.company', related='lead_id.company_id', readonly=True)

    industry = fields.Selection([
        ('logistics', 'Logistics'),
        ('property', 'Property'),
        ('hospitality', 'Hospitality'),
        ('joint_venture', 'Joint Venture'),
    ], string='Industry', required=True,
       help="Per DOCX B2: 4 industry options matching Steamships' 4 divisions + JVs")

    service_needed = fields.Selection([
        ('shipping', 'Shipping (FCL/LCL/Stevedoring/Tug)'),
        ('logistics', 'Logistics (Customs/Freight forwarding)'),
        ('property', 'Property (Office/Warehouse lease)'),
        ('hotels', 'Hotels & Hospitality (Rooms/Events)'),
        ('other', 'Other / Multiple services'),
    ], string='Service Needed', required=True,
       help="Per DOCX B2: which Steamships service the client is interested in")

    company_size = fields.Selection([
        ('sme', 'SME < 50 staff'),
        ('mid', 'Mid-market 50-200'),
        ('large', 'Large enterprise 200+'),
        ('mnc', 'Multinational'),
    ], string='Company Size', required=True)

    vessels_count = fields.Integer(string='Expected vessel calls / yr')
    cargo_volume_mt = fields.Integer(string='Expected cargo (MT/yr)')
    property_area_sqm = fields.Integer(string='Property area required (sqm)')
    hotel_room_nights = fields.Integer(string='Annual room nights')

    # KYC checklist
    ipa_cert = fields.Boolean(string='IPA Certificate of Compliance')
    ipa_cert_date = fields.Date(string='IPA Cert date')
    tax_id = fields.Boolean(string='Tax ID (TIN) verified')
    tax_id_ref = fields.Char(string='TIN reference')
    bank_ref = fields.Boolean(string='Bank reference obtained')
    bank_ref_date = fields.Date(string='Bank ref date')
    directors_id = fields.Boolean(string='Directors ID copies received')
    pep_check = fields.Boolean(string='PEP / sanctions check passed')
    credit_check = fields.Boolean(string='Credit check passed')
    insurance_cert = fields.Boolean(string='Insurance certificate valid')
    contract_signed = fields.Boolean(string='Master service agreement signed')

    completion_pct = fields.Integer(compute='_compute_completion', store=True)

    notes = fields.Html(string='Internal notes')
    onboarding_state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('kyc_done', 'KYC Complete'),
        ('approved', 'Approved - Ready for quote'),
        ('rejected', 'Rejected'),
    ], default='draft', string='Onboarding state', tracking=True)

    @api.depends('ipa_cert', 'tax_id', 'bank_ref', 'directors_id', 'pep_check',
                 'credit_check', 'insurance_cert', 'contract_signed')
    def _compute_completion(self):
        fields_to_check = ['ipa_cert', 'tax_id', 'bank_ref', 'directors_id',
                           'pep_check', 'credit_check', 'insurance_cert', 'contract_signed']
        for rec in self:
            done = sum(1 for f in fields_to_check if getattr(rec, f))
            rec.completion_pct = int(done * 100 / len(fields_to_check))

    def action_start(self):
        self.write({'onboarding_state': 'in_progress'})

    def action_mark_kyc_done(self):
        if self.completion_pct < 100:
            return
        self.write({'onboarding_state': 'kyc_done'})

    def action_approve(self):
        self.write({'onboarding_state': 'approved'})
        if self.lead_id:
            self.lead_id.message_post(
                body=f'Onboarding APPROVED. KYC {self.completion_pct}%. Ready to quote.',
                subtype_xmlid='mail.mt_note')
            # DOCX §3.1 cross-flow hook: KYC approved → CRM stage auto → Quoted
            quoted_stage = self.env.ref(
                'steamships_demo.stage_quoted', raise_if_not_found=False)
            if quoted_stage and self.lead_id.stage_id != quoted_stage:
                old_stage = self.lead_id.stage_id
                self.lead_id.stage_id = quoted_stage
                self.lead_id.message_post(
                    body=_('CRM stage auto-moved from "%s" → "%s" (KYC approved).')
                         % (old_stage.name, quoted_stage.name),
                    subtype_xmlid='mail.mt_note')

    def action_reject(self):
        self.write({'onboarding_state': 'rejected'})

    def action_reset_to_draft(self):
        """Reset to draft from any state (in_progress, kyc_done, approved).
        Allows fixing mistakes — re-runs the KYC flow from scratch."""
        for rec in self:
            old_state = rec.onboarding_state
            rec.write({'onboarding_state': 'draft'})
            rec.message_post(
                body=_('Onboarding reset to Draft (was: %s). Reason: re-running KYC.')
                     % old_state,
                subtype_xmlid='mail.mt_note')
            # If lead was auto-moved to Quoted by previous Approve, move it back.
            if rec.lead_id and rec.lead_id.stage_id.is_won is False:
                quoted_stage = rec.env.ref(
                    'steamships_demo.stage_quoted', raise_if_not_found=False)
                if (quoted_stage and rec.lead_id.stage_id == quoted_stage):
                    onboarding_stage = rec.env.ref(
                        'steamships_demo.stage_onboarding_docs', raise_if_not_found=False)
                    if onboarding_stage:
                        rec.lead_id.stage_id = onboarding_stage
                        rec.lead_id.message_post(
                            body=_('CRM stage auto-moved back to "%s" '
                                   '(Onboarding reset).') % onboarding_stage.name,
                            subtype_xmlid='mail.mt_note')

    def action_reopen_from_rejected(self):
        """Re-open a rejected onboarding: rejected -> draft."""
        for rec in self:
            if rec.onboarding_state != 'rejected':
                continue
            rec.write({'onboarding_state': 'draft'})
            rec.message_post(
                body=_('Onboarding reopened from Rejected.'),
                subtype_xmlid='mail.mt_note')
