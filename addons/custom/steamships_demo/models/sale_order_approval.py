from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


APPROVAL_THRESHOLD_PCT = 10.0  # % off list price triggers approval


class SaleOrderApprovalRequest(models.Model):
    _name = 'sale.order.approval.request'
    _description = 'Sale Order Discount Approval'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='order_id.company_id')
    requested_by = fields.Many2one('res.users', default=lambda s: s.env.user)
    requested_date = fields.Datetime(default=fields.Datetime.now)
    total_discount_pct = fields.Float(string='Avg discount %', required=True)
    total_discount_amount = fields.Monetary(string='Discount amount', required=True)
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id')
    reason = fields.Text(required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending', tracking=True)
    reviewed_by = fields.Many2one('res.users')
    reviewed_date = fields.Datetime()
    review_notes = fields.Text()

    def action_approve(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be approved.'))
        self.write({
            'state': 'approved',
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        self.order_id.write({'x_discount_approved': True})
        self.order_id.message_post(
            body=f'Discount approval GRANTED. Avg {self.total_discount_pct:.1f}%.',
            subtype_xmlid='mail.mt_note')

    def action_reject(self):
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        self.order_id.message_post(
            body=f'Discount approval REJECTED. Reason: {self.review_notes or "n/a"}',
            subtype_xmlid='mail.mt_note')

    @api.constrains('total_discount_pct')
    def _check_threshold(self):
        for rec in self:
            if rec.total_discount_pct < 0 or rec.total_discount_pct > 100:
                raise ValidationError(_('Discount must be 0-100%'))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_discount_approved = fields.Boolean(string='Discount Approved', default=False, copy=False)
    x_discount_pct = fields.Float(
        string='Avg discount %',
        compute='_compute_discount_stats', store=True,
    )
    x_discount_amount = fields.Monetary(
        string='Total discount',
        compute='_compute_discount_stats', store=True,
    )
    approval_request_ids = fields.One2many('sale.order.approval.request', 'order_id')
    approval_state = fields.Selection([
        ('not_required', 'Not required'),
        ('required', 'Required - pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='not_required', compute='_compute_approval_state', store=True)
    x_division_id = fields.Many2one('steamships.division', string='Division')
    x_branch_id = fields.Many2one('steamships.branch', string='Branch')

    @api.depends('order_line.discount', 'order_line.price_subtotal',
                 'order_line.product_id', 'order_line.price_unit')
    def _compute_discount_stats(self):
        for order in self:
            list_total = 0.0
            disc_total = 0.0
            for line in order.order_line:
                list_price = line.product_id.list_price
                if list_price and line.product_uom_qty:
                    line_list = list_price * line.product_uom_qty
                    list_total += line_list
                    disc_total += max(0.0, line_list - line.price_subtotal)
            order.x_discount_amount = disc_total
            order.x_discount_pct = (disc_total / list_total * 100.0) if list_total else 0.0

    @api.depends('x_discount_pct', 'x_discount_approved', 'approval_request_ids.state')
    def _compute_approval_state(self):
        for order in self:
            pending = order.approval_request_ids.filtered(lambda r: r.state == 'pending')
            approved = order.approval_request_ids.filtered(lambda r: r.state == 'approved')
            rejected = order.approval_request_ids.filtered(lambda r: r.state == 'rejected')
            if order.x_discount_approved or approved:
                order.approval_state = 'approved'
            elif rejected:
                order.approval_state = 'rejected'
            elif pending or (order.x_discount_pct > APPROVAL_THRESHOLD_PCT and not order.x_discount_approved):
                order.approval_state = 'required'
            else:
                order.approval_state = 'not_required'

    def action_request_discount_approval(self):
        self.ensure_one()
        if not self.x_discount_pct:
            raise UserError(_('No discount to request approval for.'))
        existing = self.approval_request_ids.filtered(lambda r: r.state == 'pending')
        if existing:
            raise UserError(_('A pending request already exists.'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request Discount Approval',
            'res_model': 'sale.order.approval.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_total_discount_pct': self.x_discount_pct,
                'default_total_discount_amount': self.x_discount_amount,
            },
        }

    def action_confirm(self):
        for order in self:
            if order.x_discount_pct > APPROVAL_THRESHOLD_PCT and not order.x_discount_approved:
                raise UserError(_(
                    'Discount %.1f%% exceeds threshold %.1f%%. '
                    'Request approval before confirming.') % (
                        order.x_discount_pct, APPROVAL_THRESHOLD_PCT))
        return super().action_confirm()
