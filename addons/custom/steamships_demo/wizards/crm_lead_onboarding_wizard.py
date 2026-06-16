from odoo import models, fields, api


class CrmLeadOnboardingWizard(models.TransientModel):
    _name = 'crm.lead.steamships.onboarding.wizard'
    _description = 'Start Onboarding Wizard'

    lead_id = fields.Many2one('crm.lead', required=True)
    industry = fields.Selection([
        ('logistics', 'Logistics'),
        ('property', 'Property'),
        ('hospitality', 'Hospitality'),
        ('joint_venture', 'Joint Venture'),
    ], required=True)
    service_needed = fields.Selection([
        ('shipping', 'Shipping (FCL/LCL/Stevedoring/Tug)'),
        ('logistics', 'Logistics (Customs/Freight forwarding)'),
        ('property', 'Property (Office/Warehouse lease)'),
        ('hotels', 'Hotels & Hospitality (Rooms/Events)'),
        ('other', 'Other / Multiple services'),
    ], required=True)
    company_size = fields.Selection([
        ('sme', 'SME < 50 staff'),
        ('mid', 'Mid-market 50-200'),
        ('large', 'Large enterprise 200+'),
        ('mnc', 'Multinational'),
    ], required=True)

    def action_create_onboarding(self):
        self.ensure_one()
        onboard = self.env['crm.lead.steamships.onboarding'].create({
            'lead_id': self.lead_id.id,
            'industry': self.industry,
            'service_needed': self.service_needed,
            'company_size': self.company_size,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead.steamships.onboarding',
            'res_id': onboard.id,
            'view_mode': 'form',
            'target': 'current',
        }
