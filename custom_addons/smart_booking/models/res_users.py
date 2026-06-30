# -*- coding: utf-8 -*-
"""Extend ``res.users`` with Google Calendar OAuth tokens.

Per-user Google Calendar OAuth tokens for the *optional* Google Calendar
push that ``smart_booking`` performs after creating the native Odoo
``calendar.event``. Tokens are tied to the Odoo user that completed the
OAuth consent — never to public visitors.

Security notes
--------------
* Tokens are stored as plain ``Char`` fields here so the prototype stays
  easy to demo. Production deployments **must** replace these with
  encrypted fields (e.g. ``fields.Char(..., password=True)`` via
  ``tools.encrypt`` / ``Vault`` / KMS) and restrict reads via
  ``ir.model.access.csv`` to a dedicated "Google Calendar Admin" group.
* ``x_google_calendar_access_token`` / ``x_google_calendar_refresh_token``
  must never be returned to the client except in the form of a
  boolean ``x_google_calendar_connected`` flag — see the views.
"""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    # TODO(security): Replace ``Char`` storage with an encrypted column
    # before production. See module docstring.
    x_google_calendar_connected = fields.Boolean(
        string="Google Calendar Connected",
        default=False,
        readonly=True,
        groups="base.group_system",
        help="True if this user has completed the Google OAuth flow and "
             "we hold a valid refresh token for their Google Calendar.",
    )
    x_google_calendar_access_token = fields.Char(
        string="Google Calendar Access Token",
        readonly=True,
        groups="base.group_system",
        help="Short-lived OAuth 2.0 access token. Refreshed automatically "
             "via the refresh token when expired. "
             "**Encryption recommended for production.**",
    )
    x_google_calendar_refresh_token = fields.Char(
        string="Google Calendar Refresh Token",
        readonly=True,
        groups="base.group_system",
        help="Long-lived OAuth 2.0 refresh token used to mint new access "
             "tokens. Treat like a password. "
             "**Encryption recommended for production.**",
    )
    x_google_calendar_token_expiry = fields.Datetime(
        string="Google Calendar Token Expiry",
        readonly=True,
        groups="base.group_system",
        help="UTC datetime at which the current access token expires.",
    )
    x_google_calendar_id = fields.Char(
        string="Google Calendar ID",
        default="primary",
        groups="base.group_system",
        help="Google Calendar ID to push events to. Defaults to 'primary' "
             "(the user's main Google Calendar).",
    )

    def _steamships_google_user_payload(self):
        """Return a safe dict describing this user's Google Calendar status.

        Safe = contains only the connected flag and calendar id; tokens
        are deliberately omitted so this payload can be rendered in any
        QWeb template.
        """
        self.ensure_one()
        return {
            "connected": bool(self.x_google_calendar_connected),
            "calendar_id": self.x_google_calendar_id or "primary",
        }
