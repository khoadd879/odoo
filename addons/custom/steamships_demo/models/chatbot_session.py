import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SteamshipsChatbotSession(models.Model):
    _name = 'steamships.chatbot.session'
    _description = 'AI Chatbot Conversation Log'
    _order = 'create_date desc'

    name = fields.Char(string='Title', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', string='User',
                              default=lambda self: self.env.user)
    mode = fields.Selection([('staff', 'Staff'), ('client', 'Client')],
                            required=True, default='staff')
    line_ids = fields.One2many('steamships.chatbot.line', 'session_id',
                               string='Conversation')
    message_count = fields.Integer(string='Messages',
                                   compute='_compute_message_count')

    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.line_ids)

    @api.depends('user_id', 'create_date')
    def _compute_name(self):
        for rec in self:
            ts = fields.Datetime.to_string(rec.create_date) if rec.create_date else ''
            rec.name = f"{rec.user_id.name or 'Anon'} — {ts}"


class SteamshipsChatbotLine(models.Model):
    _name = 'steamships.chatbot.line'
    _description = 'AI Chatbot Message'
    _order = 'create_date asc'

    session_id = fields.Many2one('steamships.chatbot.session', required=True,
                                 ondelete='cascade')
    role = fields.Selection([('user', 'User'), ('assistant', 'Assistant')],
                            required=True)
    content = fields.Text(required=True)
    source_names = fields.Char(string='Source documents cited')

    @api.model
    def _cron_cleanup_old_sessions(self, days=90):
        """Cleanup chatbot sessions older than N days (called by ir.cron)."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(),
                                          days=days)
        old = self.env['steamships.chatbot.session'].search([
            ('create_date', '<', cutoff),
        ])
        if old:
            _logger.info('Cleanup: removing %d chatbot sessions older than %d days',
                         len(old), days)
            old.unlink()
        return True
