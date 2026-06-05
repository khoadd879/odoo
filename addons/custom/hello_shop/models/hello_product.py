from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hello_tag = fields.Char(
        string='Hello Tag',
        help='Demo field added by hello_shop module to verify custom module install.',
    )
