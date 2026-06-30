# -*- coding: utf-8 -*-
"""Optional Google Calendar push helpers for Steamships Smart Booking.

This module is a *thin* wrapper around the Google Calendar REST API. It
deliberately avoids any persistent OAuth setup outside of the fields
already declared on ``res.users`` and ``calendar.event``.

Configuration
-------------
Read (in this order, first hit wins) from environment variables *or*
``ir.config_parameter``:

* ``steamships_google_calendar_client_id``
* ``steamships_google_calendar_client_secret``
* ``steamships_google_calendar_redirect_uri``

We deliberately never hard-code secrets — see the call sites in
``controllers/google_calendar.py``.

Auth model
----------
Per-user OAuth 2.0 (no service account, no domain-wide delegation) so the
event lands in the salesperson's *personal* Google Calendar. This matches
the spec: "Do not use a service account for personal Google Calendars."

Failure semantics
-----------------
Every Google API call is wrapped in try/except at the call site (the
``_create_google_calendar_event`` helper and the booking controller).
A failed push must NEVER break the Odoo booking — it merely writes a
note on the calendar.event and the chatter so the salesperson can retry
manually.
"""

import datetime
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from odoo import fields

_logger = logging.getLogger(__name__)

# --- Google Calendar API constants ----------------------------------------
GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.events"
DEFAULT_TIMEZONE = "Pacific/Port_Moresby"
TOKEN_EXPIRY_SAFETY_MARGIN = datetime.timedelta(seconds=60)


# --- Configuration helpers ------------------------------------------------
def _get_config(env, key):
    """Read a Google credential from ``ir.config_parameter`` then env.

    Returns an empty string if neither source is set so callers can decide
    how to handle a missing value.
    """
    icp_value = (
        env["ir.config_parameter"].sudo().get_param(key, default="") or ""
    )
    if icp_value:
        return icp_value
    return os.environ.get(key, "") or ""


def get_client_id(env):
    return _get_config(env, "steamships_google_calendar_client_id")


def get_client_secret(env):
    return _get_config(env, "steamships_google_calendar_client_secret")


def get_redirect_uri(env):
    return _get_config(env, "steamships_google_calendar_redirect_uri")


def is_configured(env):
    """Return True only if all three OAuth credentials are present.

    Used to disable Connect buttons and to skip the push entirely when
    Google credentials are missing — keeps the demo safe to ship without
    valid secrets.
    """
    return bool(
        get_client_id(env)
        and get_client_secret(env)
        and get_redirect_uri(env)
    )


# --- OAuth flow helpers ---------------------------------------------------
def build_authorize_url(env, state):
    """Compose the Google consent URL with ``state`` for CSRF protection.

    The ``state`` param lets us round-trip the originating Odoo user id
    so /callback can attribute the tokens to the right user even when
    ``auth="public"`` is required by Google's redirect.
    """
    params = {
        "client_id": get_client_id(env),
        "redirect_uri": get_redirect_uri(env),
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",  # prototype-only; production should drop.
        "state": state,
    }
    return "%s?%s" % (
        GOOGLE_AUTH_BASE,
        urllib.parse.urlencode({k: v for k, v in params.items() if v}),
    )


def exchange_code_for_tokens(env, code):
    """Exchange ``code`` for a token dict.

    Returns ``{"access_token": str, "refresh_token": str|None,
    "expires_in": int, "token_type": str, ...}``.
    """
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": get_client_id(env),
        "client_secret": get_client_secret(env),
        "redirect_uri": get_redirect_uri(env),
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_access_token(env, user):
    """Refresh the user's access token; update the user record.

    Returns the new access token string, or an empty string on failure.
    Never raises — caller decides how to surface the error.
    """
    refresh_token = user.x_google_calendar_refresh_token
    if not refresh_token:
        return ""
    data = urllib.parse.urlencode({
        "refresh_token": refresh_token,
        "client_id": get_client_id(env),
        "client_secret": get_client_secret(env),
        "grant_type": "refresh_token",
    }).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        _logger.exception(
            "Failed to refresh Google access token for user %s", user.id)
        return ""

    new_access = payload.get("access_token") or ""
    expires_in = payload.get("expires_in")
    update_vals = {
        "x_google_calendar_access_token": new_access,
    }
    if expires_in is not None:
        expiry_utc = (
            datetime.datetime.utcnow()
            + datetime.timedelta(seconds=int(expires_in or 3600))
            - TOKEN_EXPIRY_SAFETY_MARGIN
        )
        update_vals["x_google_calendar_token_expiry"] = (
            fields.Datetime.to_string(expiry_utc)
        )
    user.sudo().write(update_vals)
    return new_access


def _ensure_fresh_access_token(env, user):
    """Return a fresh access token for ``user`` or "" on failure.

    Refreshes the cached access token if it is missing or about to
    expire.
    """
    access = user.x_google_calendar_access_token or ""
    expiry = user.x_google_calendar_token_expiry
    needs_refresh = (
        not access
        or not expiry
        or datetime.datetime.utcnow()
        >= fields.Datetime.to_datetime(expiry) - TOKEN_EXPIRY_SAFETY_MARGIN
    )
    if needs_refresh:
        access = refresh_access_token(env, user)
    return access


def _format_iso8601_utc(dt_value):
    """Convert a ``calendar.event.start``/``stop`` to an ISO 8601 string.

    Google Calendar accepts either an RFC3339 ``dateTime`` with a
    ``timeZone`` field, or an all-day ``date``. We always send the
    timestamped form. ``dt_value`` is a naive UTC datetime coming from
    Odoo — we explicitly append ``Z`` so Google interprets it as UTC
    and applies ``timeZone`` from the event body.
    """
    dt = fields.Datetime.to_datetime(dt_value)
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        # Convert to UTC, strip tzinfo, append Z.
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_event_body(event):
    """Map an Odoo ``calendar.event`` record to a Google ``events.insert`` body."""
    attendee_emails = []
    for partner in event.partner_ids:
        email = (partner.email or "").strip().lower()
        if email and "@" in email and email not in attendee_emails:
            attendee_emails.append(email)
    body = {
        "summary": event.name or "Steamships Meeting",
        "location": event.location or "",
        "description": event.description or "",
        "start": {
            "dateTime": _format_iso8601_utc(event.start),
            "timeZone": DEFAULT_TIMEZONE,
        },
        "end": {
            "dateTime": _format_iso8601_utc(event.stop),
            "timeZone": DEFAULT_TIMEZONE,
        },
    }
    if attendee_emails:
        body["attendees"] = [{"email": e} for e in attendee_emails]
    return body


def insert_calendar_event(env, user, event_body):
    """POST an event to Google Calendar via ``events.insert``.

    Returns ``{"id": str}`` on success; returns ``{"error": str}`` on
    failure. Never raises — the caller is responsible for swallowing.
    """
    calendar_id = (
        user.x_google_calendar_id or "primary"
    ).strip() or "primary"
    url = "%s/calendars/%s/events?%s" % (
        GOOGLE_CALENDAR_API_BASE,
        urllib.parse.quote(calendar_id, safe=""),
        urllib.parse.urlencode({"sendUpdates": "none"}),
    )
    access_token = _ensure_fresh_access_token(env, user)
    if not access_token:
        return {"error": "No valid Google access token."}
    payload = json.dumps(event_body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": "Bearer %s" % access_token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            err_body = ""
        _logger.warning(
            "Google Calendar events.insert failed: HTTP %s body=%s",
            exc.code, err_body)
        return {"error": "HTTP %s: %s" % (exc.code, (err_body or "")[:500])}
    except Exception as exc:  # noqa: BLE001
        _logger.exception("Google Calendar events.insert failed")
        return {"error": str(exc)}
    return body if isinstance(body, dict) else {"error": "Bad payload"}


def push_event_to_google(env, event, user):
    """Idempotently push ``event`` to ``user``'s Google Calendar.

    This is the *single* helper the booking flow calls. It enforces:

    * Skip if the user is not connected.
    * Skip if the event has already been pushed successfully.
    * Skip if Google credentials aren't configured (e.g. dev/demo).
    * Surface errors via ``x_google_calendar_sync_error`` and a chatter
      note without ever raising.

    Returns ``True`` if a Google event id is now stored on the Odoo
    event, ``False`` otherwise.
    """
    if not user or not user.x_google_calendar_connected:
        return False
    if not is_configured(env):
        return False
    if event.x_google_calendar_event_id and event.x_google_calendar_synced:
        # Already pushed; do not create duplicates.
        return True

    event_body = build_event_body(event)
    result = insert_calendar_event(env, user, event_body)
    if not isinstance(result, dict):
        event.sudo().write({
            "x_google_calendar_sync_error": "Google API returned no body.",
        })
        return False
    if "error" in result:
        err_msg = result["error"] or "Unknown Google API error."
        event.sudo().write({
            "x_google_calendar_synced": False,
            "x_google_calendar_sync_error": err_msg,
        })
        # Post a chatter note on the linked lead if any.
        try:
            lead = event.x_steamships_lead_id
            if lead and lead.exists():
                lead.message_post(
                    body=(
                        "<b>⚠️ Google Calendar push failed</b><br/>"
                        "Event: <a href='/web#id=%s&model=calendar.event"
                        "&view_type=form'>%s</a><br/>"
                        "Error: %s" % (
                            event.id,
                            event.display_name,
                            err_msg.replace("\n", "<br/>"),
                        )
                    ),
                    subject="Google Calendar push failed",
                    subtype_xmlid="mail.mt_note",
                )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Failed to post Google sync error note on lead")
        return False

    google_event_id = result.get("id") or ""
    event.sudo().write({
        "x_google_calendar_event_id": google_event_id,
        "x_google_calendar_synced": bool(google_event_id),
        "x_google_calendar_sync_error": False,
    })
    return True


def make_signed_state(env, user_id):
    """Return an opaque, signed ``state`` value for OAuth round-trip.

    Format: ``"<user_id>:<hmac>"``. We use the database secret
    (``database.secret``) when available, falling back to a HMAC keyed
    by ``ir.config_parameter`` ``database.uuid`` (always seeded) so the
    value is non-guessable without an attacker already having full
    database access.

    We deliberately avoid raising if neither secret is available; in that
    case the state will still carry the user_id but with a static
    fallback marker so the callback can refuse to act.
    """
    import hmac
    import hashlib

    secret = env["res.config.settings"].sudo().get_database_secret() or ""
    if not secret:
        # ``database.uuid`` is seeded by Odoo on first init; never empty.
        secret = (
            env["ir.config_parameter"].sudo().get_param(
                "database.uuid", default="") or ""
        )
    if not secret:
        # Last-resort: empty secret leaves the state user-trust only via
        # session, which is fine because /callback uses auth="user".
        mac = ""
    else:
        mac = hmac.new(
            secret.encode("utf-8"),
            str(user_id).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]
    return "%s:%s" % (user_id, mac)


def verify_signed_state(env, state, expected_user_id):
    """Validate ``state`` matches ``expected_user_id``.

    Returns True if the embedded user id matches *and* the MAC verifies
    when a secret is available. When no secret is available, returns
    True if the user id matches — this is acceptable because the OAuth
    callback always goes through Odoo auth="user" which itself validates
    the session.
    """
    import hmac
    import hashlib

    try:
        user_id_str, mac = state.split(":", 1)
        user_id_int = int(user_id_str)
    except (ValueError, AttributeError):
        return False
    if user_id_int != expected_user_id:
        return False
    secret = env["res.config.settings"].sudo().get_database_secret() or ""
    if not secret:
        secret = (
            env["ir.config_parameter"].sudo().get_param(
                "database.uuid", default="") or ""
        )
    if not secret:
        # No secret to compare against; rely on Odoo session auth.
        return True
    expected_mac = hmac.new(
        secret.encode("utf-8"),
        str(expected_user_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    return hmac.compare_digest(mac, expected_mac)
