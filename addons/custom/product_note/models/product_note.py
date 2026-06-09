from odoo import models, fields, api


class ProductNote(models.Model):
    _name = 'product.note'
    _description = 'Product Internal Note'
    _order = 'create_date desc'

    name = fields.Char(
        string='Title',
        required=True,
    )
    body = fields.Text(
        string='Note Content',
    )
    product_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        ondelete='cascade',
    )
    author_id = fields.Many2one(
        'res.users',
        string='Author',
        default=lambda self: self.env.user,
        readonly=True,
    )
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
    ], string='Priority', default='1')

    @api.model
    def create(self, vals):
        # Auto-fill name when user does not provide one
        if not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].next_by_code('product.note') or 'New Note'
        return super().create(vals)
