{
    'name': 'Mail Gmail Setup',
    'version': '18.0.1.0.0',
    'summary': 'Provision Gmail SMTP outgoing mail server from env vars',
    'description': """
Reads MAIL_SMTP_* env vars (set in docker-compose.yml from .env) and creates /
updates an `ir.mail_server` record on module install so Odoo can send mail via
Gmail. Source of truth for credentials: `.env` at project root (synced from
ielts_training_app/.env).
""",
    'depends': ['mail'],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'author': 'Local Dev',
    'license': 'LGPL-3',
}
