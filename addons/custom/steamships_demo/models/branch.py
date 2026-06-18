from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


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

    @api.constrains('name')
    def _check_name_not_empty(self):
        """B1 fix: translate=True stores jsonb, bypasses required=True."""
        for rec in self:
            if not rec.name or not any(
                v and str(v).strip() for v in rec.name.values()
            ) if isinstance(rec.name, dict) else not (rec.name and rec.name.strip()):
                raise ValidationError(_('Branch name cannot be empty.'))
