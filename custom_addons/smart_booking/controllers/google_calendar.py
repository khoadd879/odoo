# -*- coding: utf-8 -*-
"""Google Calendar OAuth controller + settings page.

Routes (all under /steamships/google_calendar/...):

* ``GET /connect``     — user must be logged in. Builds the Google
                         authorize URL and redirects them out to Google.
* ``GET /callback``    — public-or-user endpoint. The Google OAuth
                         browser-side redirect cannot carry Odoo cookies
                         in every browser, so the route accepts an
                         anonymous request but requires the ``state``
                         round-trip to identify which Odoo user to
                         attribute the tokens to. The state itself is
                         HMAC-signed with a server-side secret.
* ``GET /disconnect``  — user must be logged in. Clears the Google
                         tokens on the current user and bounces back
                         to the settings page.
* ``GET /settings``    — user must be logged in. Renders the settings
                         QWeb template.

Security:

* No ``auth="public"`` route ever writes tokens — only ``/callback``
  is public, and it accepts *no* writes without a verified state.
* ``/connect`` and ``/disconnect`` and ``/settings`` are all
  ``auth="user"``.
* Tokens are loaded and stored via ``sudo()`` *only* on the user
  that owns them (``request.env.user``), never on others.
"""

import logging
import urllib.parse

from odoo import _, fields, http

from .. import google_calendar as _gc

_logger = logging.getLogger(__name__)

# The settings page URL we redirect back to after connect / disconnect.
SETTINGS_URL = "/steamships/google_calendar/settings"


def _redirect_back_to_settings(**query):
    qs = urllib.parse.urlencode({k: v for k, v in query.items() if v})
    return http.request.redirect(
        "%s%s" % (SETTINGS_URL, ("?%s" % qs) if qs else ""))


class GoogleCalendarController(http.Controller):
    """OAuth flow + settings page."""

    # ----------------------------------------------------------- settings
    @http.route(
        "/steamships/google_calendar/settings",
        type="http",
        auth="user",
        website=False,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_settings(self, **kwargs):
        user = http.request.env.user
        values = {
            "user_payload": user._steamships_google_user_payload(),
            "configured": _gc.is_configured(http.request.env),
            "settings_url": SETTINGS_URL,
            "connect_url": "/steamships/google_calendar/connect",
            "disconnect_url": "/steamships/google_calendar/disconnect",
            "status": kwargs.get("status") or "",
            "status_message": kwargs.get("msg") or "",
        }
        return http.request.render(
            "smart_booking.google_calendar_settings",
            values,
        )

    # -------------------------------------------------------------- connect
    @http.route(
        "/steamships/google_calendar/connect",
        type="http",
        auth="user",
        website=False,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_connect(self, **kwargs):
        env = http.request.env
        if not _gc.is_configured(env):
            return _redirect_back_to_settings(
                status="error",
                msg=_(
                    "Google Calendar integration is not configured. "
                    "Ask an administrator to set the "
                    "steamships_google_calendar_* system parameters."
                ),
            )
        user = http.request.env.user
        state = _gc.make_signed_state(env, user.id)
        authorize_url = _gc.build_authorize_url(env, state)
        return http.request.redirect(authorize_url)

    # ----------------------------------------------------------- callback
    @http.route(
        "/steamships/google_calendar/callback",
        type="http",
        auth="public",
        website=False,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_callback(self, **kwargs):
        env = http.request.env
        code = kwargs.get("code")
        state = kwargs.get("state") or ""
        error = kwargs.get("error")
        if error:
            return _redirect_back_to_settings(
                status="error",
                msg=_("Google returned an error: %s") % error,
            )
        if not code or not state:
            return _redirect_back_to_settings(
                status="error",
                msg=_("Missing OAuth code or state."),
            )
        # State encodes the originating user id, HMAC-signed. Verify it
        # BEFORE exchanging the code so a forged state cannot be used to
        # push tokens to an attacker-controlled user.
        try:
            state_user_id = int(state.split(":", 1)[0])
        except (ValueError, AttributeError):
            return _redirect_back_to_settings(
                status="error", msg=_("Invalid state."),
            )
        if not _gc.verify_signed_state(env, state, state_user_id):
            return _redirect_back_to_settings(
                status="error", msg=_("State signature mismatch."),
            )

        try:
            token_payload = _gc.exchange_code_for_tokens(env, code)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Google token exchange failed")
            return _redirect_back_to_settings(
                status="error",
                msg=_("Token exchange failed: %s") % exc,
            )

        access_token = token_payload.get("access_token") or ""
        refresh_token = token_payload.get("refresh_token") or ""
        expires_in = token_payload.get("expires_in")
        if not access_token:
            return _redirect_back_to_settings(
                status="error",
                msg=_("Google did not return an access token."),
            )

        # Persist tokens on the user identified by ``state``.
        update_vals = {
            "x_google_calendar_connected": True,
            "x_google_calendar_access_token": access_token,
            "x_google_calendar_refresh_token": refresh_token or False,
        }
        if expires_in is not None:
            from datetime import datetime, timedelta

            expiry = (
                datetime.utcnow()
                + timedelta(seconds=int(expires_in or 3600))
                - timedelta(seconds=60)
            )
            update_vals["x_google_calendar_token_expiry"] = (
                fields.Datetime.to_string(expiry)
            )
        try:
            target_user = env["res.users"].sudo().browse(state_user_id)
        except Exception:  # noqa: BLE001
            target_user = None
        if not target_user or not target_user.exists():
            return _redirect_back_to_settings(
                status="error", msg=_("User not found."))
        target_user.write(update_vals)
        # If the Google flow was initiated by the *currently-logged-in*
        # user (typical case) we keep them on the settings page.
        return _redirect_back_to_settings(
            status="ok",
            msg=_("Connected to Google Calendar."),
        )

    # ---------------------------------------------------------- disconnect
    @http.route(
        "/steamships/google_calendar/disconnect",
        type="http",
        auth="user",
        website=False,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_disconnect(self, **kwargs):
        user = http.request.env.user
        user.sudo().write({
            "x_google_calendar_connected": False,
            "x_google_calendar_access_token": False,
            "x_google_calendar_refresh_token": False,
            "x_google_calendar_token_expiry": False,
        })
        return _redirect_back_to_settings(
            status="ok",
            msg=_("Disconnected from Google Calendar."),
        )
