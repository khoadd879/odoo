from odoo import models, fields, api


class SteamshipsBranch(models.Model):
    _name = 'steamships.branch'
    _description = 'Steamships Branch / Office'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, size=8)
    division_id = fields.Many2one('steamships.division', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    address = fields.Char()
    phone = fields.Char()
    email = fields.Char()
    manager_id = fields.Many2one('res.users', string='Branch Manager')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code, company_id)', 'Branch code must be unique per company.'),
    ]
