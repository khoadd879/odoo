from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    onboarding_id = fields.Many2one(
        'crm.lead.steamships.onboarding',
        string='Onboarding / KYC',
        compute='_compute_onboarding',
        store=True,
    )
    onboarding_state = fields.Selection(related='onboarding_id.onboarding_state', string='KYC state', readonly=True)
    onboarding_completion = fields.Integer(related='onboarding_id.completion_pct', string='KYC %', readonly=True)
    steamships_division_id = fields.Many2one('steamships.division', string='Steamships Division')
    steamships_branch_id = fields.Many2one('steamships.branch', string='Branch of interest')

    def _compute_onboarding(self):
        for lead in self:
            ob = self.env['crm.lead.steamships.onboarding'].search(
                [('lead_id', '=', lead.id)], limit=1)
            lead.onboarding_id = ob

    def action_start_onboarding(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Start Customer Onboarding',
            'res_model': 'crm.lead.steamships.onboarding.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_id': self.id},
        }

    def action_open_onboarding(self):
        self.ensure_one()
        if not self.onboarding_id:
            return self.action_start_onboarding()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead.steamships.onboarding',
            'res_id': self.onboarding_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
