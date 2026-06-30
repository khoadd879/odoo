# -*- coding: utf-8 -*-
"""Public booking controller for Steamships.

Three routes:

* ``GET  /steamships/booking``        — public booking page (QWeb).
* ``POST /steamships/booking/submit`` — creates partner / event / chatter post.
* ``GET  /steamships/booking/thanks`` — thank-you page with Google Calendar link.

All routes are public (no login). The submit endpoint only:

1. Reads lightweight whitelisted form fields.
2. Looks up (or creates) a ``res.partner`` by email using ``sudo()`` only on the
   minimum required ``res.partner.create`` call.
3. Creates a ``calendar.event`` with ``sudo()`` so a guest can book without
   having calendar / CRM write access.
4. If a ``lead_id`` was supplied, posts a chatter note + scheduled activity
   using ``sudo()`` only on the specific lead.

The lead fields exposed to the public form are restricted to a small whitelist:
``name``, ``contact_name``, ``partner_name``, ``email_from``, ``function``,
``phone``. Private / financial fields are never read from the lead.
"""

import datetime
import logging
import urllib.parse

from odoo import _, fields, http
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# --- Demo schedule -------------------------------------------------------
# Slots are fixed Monday-Friday in Pacific/Port_Moresby (UTC+10/+11).
# We work in naive UTC datetimes inside Odoo and let the client convert to
# its local timezone for display.
PNG_TZ_OFFSET_HOURS = 10  # PNG is UTC+10, no DST.
DURATION_MINUTES = {
    "sales_call_30": 30,
    "onboarding_60": 60,
}
MEETING_TYPE_LABELS = {
    "sales_call_30": "Sales Call (30 min)",
    "onboarding_60": "Client Onboarding (60 min)",
}
TIMEZONE_OPTIONS = [
    "Pacific/Port_Moresby",
    "Asia/Singapore",
    "Asia/Ho_Chi_Minh",
    "Australia/Sydney",
]
PUBLIC_TZ_WHITELIST = ("Pacific/Port_Moresby", "Asia/Singapore",
                       "Asia/Ho_Chi_Minh", "Australia/Sydney")
# Fields on crm.lead that the public form is allowed to prefill from.
# Whitelisted to avoid leaking private/financial info.
PUBLIC_LEAD_FIELDS = (
    "id", "name", "contact_name", "partner_name",
    "email_from", "function", "phone",
)


def _png_local_to_utc(local_naive_dt):
    """Convert a naive 'PNG local' datetime into a naive UTC datetime."""
    return local_naive_dt - datetime.timedelta(hours=PNG_TZ_OFFSET_HOURS)


def _google_calendar_url(event, client_tz_label):
    """Return a Google Calendar template URL for a calendar.event record.

    No OAuth — just the public ``calendar.google.com/calendar/render`` URL
    prefilled via query string (the "Template" approach).
    """
    base = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    start_dt = fields.Datetime.to_datetime(event.start)
    stop_dt = fields.Datetime.to_datetime(event.stop)
    # Google Calendar template expects UTC dates in YYYYMMDDTHHMMSSZ form.
    google_dates = "/".join([
        start_dt.strftime("%Y%m%dT%H%M%SZ"),
        stop_dt.strftime("%Y%m%dT%H%M%SZ"),
    ])
    title = event.name or "Steamships Meeting"
    details_parts = [
        event.description or "",
        "",
        "Timezone shown: %s" % client_tz_label,
        "Steamships base timezone: Pacific/Port_Moresby",
    ]
    details = "\n".join(p for p in details_parts if p is not None).strip()
    params = {
        "text": title,
        "dates": google_dates,
        "details": details,
    }
    return base + "&" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _build_demo_slots():
    """Return a list of dicts describing the fixed demo slots in PNG time.

    Each entry: { "label_png": "Mon 09:00", "weekday": 0, "hour": 9,
                  "minute": 0 }. Slots are valid Monday=0 .. Friday=4.
    """
    fixed_hours = [(9, 0), (10, 0), (11, 0), (14, 0), (15, 0), (16, 0)]
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    return [
        {"weekday": wd, "weekday_label": weekday_labels[wd],
         "hour": h, "minute": m, "label_png": "%s %02d:%02d" % (weekday_labels[wd], h, m)}
        for wd in range(0, 5) for h, m in fixed_hours
    ]


def _resolve_slot_iso(slot_key):
    """Resolve a "<weekday>_<HH>_<MM>" key to a PNG-local datetime + UTC datetime.

    The slot_key is the slot displayed in the visitor timezone but stored in
    PNG time on the server. We accept either the raw PNG slot or its
    visitor-local counterpart by re-interpreting the key parts.

    For demo simplicity we treat each slot key as the PNG-local slot.
    """
    try:
        weekday_str, hh_str, mm_str = slot_key.split("_")
        weekday = int(weekday_str)
        hh = int(hh_str)
        mm = int(mm_str)
    except (ValueError, AttributeError):
        raise ValidationError(_("Invalid slot selection."))
    if weekday < 0 or weekday > 4:
        raise ValidationError(_("Slot must be Monday to Friday."))
    # Today at 00:00 PNG local, then offset to next given weekday.
    today_png = (datetime.datetime.utcnow()
                 + datetime.timedelta(hours=PNG_TZ_OFFSET_HOURS)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    # Find next valid weekday (>= today).
    days_ahead = (weekday - today_png.weekday()) % 7
    if days_ahead == 0:
        # Same weekday — only valid if slot is later today; else roll 7 days.
        candidate = today_png.replace(hour=hh, minute=mm)
        if candidate <= today_png:
            days_ahead = 7
    slot_png_local = today_png + datetime.timedelta(days=days_ahead)
    slot_png_local = slot_png_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    slot_utc_naive = _png_local_to_utc(slot_png_local)
    return slot_png_local, slot_utc_naive.replace(tzinfo=None)


class SteamshipsBookingController(http.Controller):
    """Public booking flow."""

    # ----------------------------------------------------------------- page
    @http.route(
        "/steamships/booking",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def booking_page(self, **kwargs):
        lead_id = kwargs.get("lead_id")
        prefilled = {"name": "", "email": "", "company": "",
                     "phone": "", "lead_id": ""}
        if lead_id:
            try:
                lead_id_int = int(lead_id)
            except (TypeError, ValueError):
                lead_id_int = None
            if lead_id_int:
                # Read only safe fields on the lead. We use ``search()`` so
                # we never blow up with KeyError if the lead id is missing.
                lead_set = http.request.env["crm.lead"].sudo().search(
                    [("id", "=", lead_id_int)], limit=1)
                if lead_set:
                    lead = lead_set.read(PUBLIC_LEAD_FIELDS)[0]
                    prefilled = {
                        "name": lead.get("contact_name") or lead.get("name") or "",
                        "email": lead.get("email_from") or "",
                        "company": lead.get("partner_name") or "",
                        "phone": lead.get("phone") or "",
                        "lead_id": str(lead["id"]),
                    }

        return http.request.render(
            "steamships_booking.booking_page",
            {
                "prefilled": prefilled,
                "meeting_types": MEETING_TYPE_LABELS,
                "timezones": TIMEZONE_OPTIONS,
                "slots": _build_demo_slots(),
            },
        )

    # --------------------------------------------------------------- submit
    @http.route(
        "/steamships/booking/submit",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["POST"],
        csrf=True,
    )
    def booking_submit(self, **post):
        # Strict field whitelist — never trust unexpected keys.
        meeting_type = (post.get("meeting_type") or "").strip()
        name = (post.get("name") or "").strip()
        email = (post.get("email") or "").strip().lower()
        company = (post.get("company") or "").strip()
        timezone_name = (post.get("timezone") or "").strip()
        slot_key = (post.get("slot") or "").strip()
        notes = (post.get("notes") or "").strip()
        lead_id_raw = (post.get("lead_id") or "").strip()

        if meeting_type not in DURATION_MINUTES:
            raise ValidationError(_("Please pick a valid meeting type."))
        if not name or not email:
            raise ValidationError(_("Name and email are required."))
        if timezone_name not in PUBLIC_TZ_WHITELIST:
            raise ValidationError(_("Please pick a supported timezone."))
        if "@" not in email:
            raise ValidationError(_("Please provide a valid email."))

        # Resolve slot to a real UTC datetime.
        slot_png_local, slot_utc_naive = _resolve_slot_iso(slot_key)
        duration_minutes = DURATION_MINUTES[meeting_type]
        slot_stop_utc_naive = slot_utc_naive + datetime.timedelta(
            minutes=duration_minutes)
        # Odoo stores calendar.event.start/stop as naive UTC datetimes.
        start_utc = fields.Datetime.to_string(slot_utc_naive)
        stop_utc = fields.Datetime.to_string(slot_stop_utc_naive)

        # Find or create partner. Use sudo() so a public user can write.
        Partner = http.request.env["res.partner"].sudo()
        partner = Partner.search([("email", "=ilike", email)], limit=1)
        if not partner:
            partner_name = company or name
            partner = Partner.create({
                "name": partner_name,
                "email": email,
                "company_name": company or False,
                "is_company": bool(company),
                "type": "contact",
            })
        else:
            # If partner exists, make sure the supplied name/company is captured.
            update_vals = {}
            if name and not partner.name:
                update_vals["name"] = name
            if company and not partner.company_name and not partner.is_company:
                update_vals["company_name"] = company
            if update_vals:
                partner.write(update_vals)

        # Optional associated lead — must exist and be a lead.
        lead = None
        lead_id = None
        if lead_id_raw:
            try:
                lead_id = int(lead_id_raw)
            except (TypeError, ValueError):
                lead_id = None
            if lead_id:
                lead = http.request.env["crm.lead"].sudo().browse(lead_id)
                if not lead.exists():
                    lead = None
                    lead_id = None

        # Compose event description with safe formatting.
        meeting_label = MEETING_TYPE_LABELS[meeting_type]
        event_name = "%s — %s" % (
            meeting_label, (company or name or email).strip())
        description_lines = [
            "Booked via Steamships Smart Booking.",
            "",
            "Name: %s" % name,
            "Email: %s" % email,
            "Company: %s" % (company or "—"),
            "Client timezone: %s" % timezone_name,
            "Steamships base timezone: Pacific/Port_Moresby",
            "",
            "Notes: %s" % (notes or "—"),
        ]
        if lead:
            description_lines.append("")
            description_lines.append("Related CRM lead: %s (ID %s)" % (
                lead.name or "", lead.id))
        description = "\n".join(description_lines)

        # Create calendar.event with sudo() (guest users have no calendar
        # write access by default). ``duration`` is computed from start/stop,
        # so we do not write it.
        Event = http.request.env["calendar.event"].sudo()
        event_vals = {
            "name": event_name,
            "start": start_utc,
            "stop": stop_utc,
            "description": description,
            "partner_ids": [(6, 0, [partner.id])],
        }
        event = Event.create(event_vals)

        # Post chatter / activity on the related lead, if any.
        if lead:
            try:
                chatter_body = _(
                    "📅 Booking confirmed: <b>%(meeting)s</b><br/>"
                    "Slot: %(slot_png)s — %(slot_stop_png)s (PNG time)<br/>"
                    "Client timezone: %(tz)s<br/>"
                    "Client: %(name)s &lt;%(email)s&gt; — %(company)s<br/>"
                    "Calendar event: %(event_name)s"
                ) % {
                    "meeting": meeting_label,
                    "slot_png": slot_png_local.strftime("%a %d %b %H:%M"),
                    "slot_stop_png": (slot_png_local + datetime.timedelta(
                        minutes=duration_minutes)).strftime("%H:%M"),
                    "tz": timezone_name,
                    "name": name,
                    "email": email,
                    "company": company or "—",
                    "event_name": event.display_name,
                }
                lead.message_post(
                    body=chatter_body,
                    subject=_("New booking: %s") % meeting_label,
                    subtype_xmlid="mail.mt_note",
                )
                # Schedule a follow-up activity so the sales rep is reminded.
                lead.activity_schedule(
                    activity_type_xmlid="mail.mail_activity_data_todo",
                    summary=_("Follow up on booked %s") % meeting_label,
                    note=_("Lead booked %s at %s (PNG). "
                           "Calendar event: %s")
                          % (meeting_label,
                             slot_png_local.strftime("%a %H:%M"),
                             event.display_name),
                    date_deadline=slot_utc_naive.date(),
                )
            except Exception:  # noqa: BLE001
                # Chatter / activity is best-effort; do not break booking.
                _logger.exception(
                    "Failed to post chatter on lead %s", lead_id)

        # Redirect to thank-you page with the event id.
        return http.request.redirect(
            "/steamships/booking/thanks?event_id=%s" % event.id)

    # ----------------------------------------------------------- thank-you
    @http.route(
        "/steamships/booking/thanks",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def booking_thanks(self, **kwargs):
        event_id_raw = kwargs.get("event_id") or ""
        event = None
        try:
            event_id = int(event_id_raw)
        except (TypeError, ValueError):
            event_id = None

        # Read only safe fields on the event for the thank-you page.
        safe_fields = ("id", "name", "start", "stop", "duration",
                       "description", "display_name")
        if event_id:
            event_set = http.request.env["calendar.event"].sudo().search(
                [("id", "=", event_id)], limit=1)
            if event_set:
                events = event_set.read(safe_fields)
                if events:
                    event = events[0]
                    # Convert UTC to PNG (+10) and pre-compute simple UTC
                    # string labels for the template.
                    start_dt = fields.Datetime.to_datetime(event["start"])
                    stop_dt = fields.Datetime.to_datetime(event["stop"])
                    png_tz = datetime.timezone(datetime.timedelta(
                        hours=PNG_TZ_OFFSET_HOURS))
                    event["start_png"] = start_dt.replace(tzinfo=png_tz)
                    event["stop_png"] = stop_dt.replace(tzinfo=png_tz)
                    # Plain-text label of UTC start for the "Stored (UTC)" row.
                    event["start_utc_label"] = (
                        start_dt.strftime("%Y-%m-%d %H:%M") + " UTC")
                    event["start_png_label"] = event["start_png"].strftime(
                        "%A, %d %b %Y %H:%M")
                    event["stop_png_label"] = event["stop_png"].strftime(
                        "%H:%M")
                    # Re-browse to get a recordset for the URL helper.
                    event_obj = event_set
                    # Try to read the client timezone from the description.
                    tz_label = "Pacific/Port_Moresby"
                    desc = event.get("description") or ""
                    if isinstance(desc, str):
                        for line in desc.splitlines():
                            if line.startswith("Client timezone:"):
                                tz_label = line.split(":", 1)[1].strip()
                                break
                    event["google_url"] = _google_calendar_url(event_obj, tz_label)

        return http.request.render(
            "steamships_booking.booking_thanks",
            {
                "event": event,
                "meeting_types": MEETING_TYPE_LABELS,
            },
        )
