from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SteamshipsDivision(models.Model):
    _name = 'steamships.division'
    _description = 'Steamships Business Division'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, size=8, help="Short code: SHIP, PROP, HOTL, LOGI")
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    color = fields.Integer(default=0)

    branch_ids = fields.One2many('steamships.branch', 'division_id', string='Branches')
    branch_count = fields.Integer(compute='_compute_branch_count')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Division code must be unique.'),
    ]

    @api.constrains('name')
    def _check_name_not_empty(self):
        """B1 fix: translate=True stores jsonb, bypasses required=True.
        Validate that at least one translation has a non-empty name."""
        for rec in self:
            if not rec.name or not any(
                v and str(v).strip() for v in rec.name.values()
            ) if isinstance(rec.name, dict) else not (rec.name and rec.name.strip()):
                raise ValidationError(_('Division name cannot be empty.'))

    def _compute_branch_count(self):
        for div in self:
            div.branch_count = len(div.branch_ids)

    def action_open_branches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Branches',
            'res_model': 'steamships.branch',
            'view_mode': 'list,form',
            'domain': [('division_id', '=', self.id)],
        }
