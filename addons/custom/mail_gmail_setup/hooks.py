"""Post-install hook: provision Gmail SMTP outgoing mail server.

Reads MAIL_SMTP_* env vars (injected by docker-compose from .env) and writes
an `ir.mail_server` record. Idempotent — re-runs upsert by (host, user).
"""
import logging
import os

_logger = logging.getLogger(__name__)

REQUIRED = ('MAIL_SMTP_HOST', 'MAIL_SMTP_PORT', 'MAIL_SMTP_USER', 'MAIL_SMTP_PASSWORD')


def post_init_hook(env):
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        _logger.warning(
            "[mail_gmail_setup] Skipping — missing env vars: %s. "
            "Set them in .env and reinstall this module.",
            ', '.join(missing),
        )
        return

    host = os.environ['MAIL_SMTP_HOST']
    port = int(os.environ['MAIL_SMTP_PORT'])
    user = os.environ['MAIL_SMTP_USER']
    password = os.environ['MAIL_SMTP_PASSWORD']
    from_addr = os.environ.get('MAIL_SMTP_FROM') or user
    from_name = os.environ.get('MAIL_SMTP_FROM_NAME') or 'Odoo'

    MailServer = env['ir.mail_server']

    existing = MailServer.with_context(active_test=False).search([
        ('smtp_host', '=', host),
        ('smtp_user', '=', user),
    ], limit=1)

    # Odoo 18 fields:
    #   smtp_encryption: 'none' | 'ssl' | 'starttls'   (port 465=ssl, 587=starttls)
    #   smtp_authentication: 'login' | 'cram_md5' | 'none'
    #   from_filter: comma-separated local-part patterns or full emails
    vals = {
        'name': 'Gmail SMTP',
        'smtp_host': host,
        'smtp_port': port,
        'smtp_user': user,
        'smtp_pass': password,
        'smtp_authentication': 'login',
        'smtp_encryption': 'ssl' if port == 465 else 'starttls',
        'from_filter': from_addr,
        'active': True,
        'sequence': 10,
    }

    if existing:
        existing.write(vals)
        _logger.info("[mail_gmail_setup] Updated ir.mail_server id=%s (%s)", existing.id, host)
    else:
        rec = MailServer.create(vals)
        _logger.info("[mail_gmail_setup] Created ir.mail_server id=%s (%s)", rec.id, host)

    # System-wide default "from" for flows without explicit author.
    IrConfig = env['ir.config_parameter']
    IrConfig.set_param('mail.default.from', f'"{from_name}" <{from_addr}>')
    domain = from_addr.split('@', 1)[1] if '@' in from_addr else ''
    if domain:
        IrConfig.set_param('mail.catchall.domain', domain)
    _logger.info(
        "[mail_gmail_setup] Set default from=%s <%s>",
        from_name, from_addr,
    )
