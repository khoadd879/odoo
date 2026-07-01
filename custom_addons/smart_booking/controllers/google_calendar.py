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
        # ``website=True`` so Odoo binds ``request.website``; otherwise the
        # ``website.layout`` wrapper raises ``KeyError: 'website'`` when
        # rendering this qweb template on a route that does not opt in.
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_settings(self, **kwargs):
        """Render the Google Calendar settings page in a fail-safe way.

        Never raises 500 — every external dependency (config parameters,
        optional user fields, optional Google credentials) is read
        defensively with sensible defaults so the page always renders.
        """
        env = http.request.env
        user = env.user

        # ---- Read Google OAuth config (all optional). -----------------
        # ``get_param`` in Odoo 19 has odd cache/timeout behavior on some
        # ``auth="user"`` routes, so we look up the row directly via sudo().
        ICP = env["ir.config_parameter"].sudo()
        def _icp_value(key):
            rec = ICP.search([("key", "=", key)], limit=1)
            if not rec:
                return ""
            return rec.value or ""
        client_id = _icp_value("steamships_google_calendar_client_id")
        client_secret = _icp_value("steamships_google_calendar_client_secret")
        redirect_uri = _icp_value("steamships_google_calendar_redirect_uri")

        missing_keys = []
        if not client_id:
            missing_keys.append("steamships_google_calendar_client_id")
        if not client_secret:
            missing_keys.append("steamships_google_calendar_client_secret")
        if not redirect_uri:
            missing_keys.append("steamships_google_calendar_redirect_uri")
        configured = not missing_keys

        # ---- User connection state (defensive against missing fields). -
        # The module declares ``x_google_calendar_*`` on ``res.users``, but
        # if for some reason a runtime loaded the module without those
        # fields, treat the user as not-connected rather than 500ing.
        try:
            connected = bool(user.x_google_calendar_connected)
        except Exception:  # noqa: BLE001
            connected = False
        try:
            calendar_id_val = user.x_google_calendar_id or "primary"
        except Exception:  # noqa: BLE001
            calendar_id_val = "primary"

        # ---- Whitelisted payload for the template. --------------------
        # Tokens are deliberately omitted — only booleans and IDs.
        user_payload = {
            "connected": connected,
            "calendar_id": calendar_id_val,
        }

        values = {
            "user_payload": user_payload,
            # ``sb_configured`` is namespaced to avoid collisions with any
            # ``configured`` value that may already live in the qweb render
            # context (e.g. via the website module's request middleware).
            "configured": configured,
            "sb_configured": configured,
            "missing_keys": missing_keys,
            "client_id_configured": bool(client_id),
            "client_secret_configured": bool(client_secret),
            "redirect_uri": redirect_uri or "",
            "connected": connected,
            "calendar_id": calendar_id_val,
            "sync_error": "",
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
        # Bind ``request.website`` so the response / render context has a
        # website record; only the ``/connect`` route needs ``auth="user"``
        # but may not actually render a template (it 302-redirects to Google
        # when configured) so we keep it consistent with /settings.
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def google_calendar_connect(self, **kwargs):
        env = http.request.env
        # ---- Fail-safe: validate every required OAuth config key. ----
        # ``is_configured`` checks the three keys; the per-key check below
        # produces a clearer error message naming exactly which one is missing.
        missing = []
        for label, getter in (
            ("client_id",
             lambda: _gc.get_client_id(env)),
            ("client_secret",
             lambda: _gc.get_client_secret(env)),
            ("redirect_uri",
             lambda: _gc.get_redirect_uri(env)),
        ):
            try:
                if not (getter() or ""):
                    missing.append(label)
            except Exception:  # noqa: BLE001
                missing.append(label)
        if missing:
            return _redirect_back_to_settings(
                status="error",
                msg=_(
                    "Google Calendar integration is not configured. "
                    "Missing system parameters: %(keys)s. Ask an "
                    "administrator to set the "
                    "steamships_google_calendar_* system parameters."
                ) % {
                    "keys": ", ".join(
                        "steamships_google_calendar_%s" % m for m in missing),
                },
            )
        # ---- Build the signed state and Google authorize URL. ----
        # Both helpers are defensive — if they raise unexpectedly we land
        # back on the settings page with a clear message instead of 500.
        user = env.user
        try:
            state = _gc.make_signed_state(env, user.id)
            authorize_url = _gc.build_authorize_url(env, state)
        except Exception as exc:  # noqa: BLE001
            _logger.exception(
                "Failed to build Google OAuth authorize URL")
            return _redirect_back_to_settings(
                status="error",
                msg=_(
                    "Could not start Google Calendar OAuth: %s") % exc,
            )
        # ``local=False`` so Odoo 19 does NOT strip the scheme/netloc from
        # the absolute Google URL. With the default ``local=True`` the
        # helper rewrites ``https://accounts.google.com/o/oauth2/v2/auth``
        # into a same-host path ``/o/oauth2/v2/auth`` and the browser
        # 404s against Odoo instead of bouncing out to Google.
        return http.request.redirect(authorize_url, local=False)

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
        website=True,
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
