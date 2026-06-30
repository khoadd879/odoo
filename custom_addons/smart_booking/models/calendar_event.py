# -*- coding: utf-8 -*-
"""Extend ``calendar.event`` with Steamships Smart Booking markers.

The public booking flow (``smart_booking.controllers.main``) creates real
``calendar.event`` records so they appear in the native Odoo Calendar and
in the internal "Smart Booking" dashboard. The fields below are the
bookkeeping glue that lets us:

* Filter the calendar / list / form actions to only Steamships bookings
  via ``x_steamships_booking``.
* Link each booking back to its source ``crm.lead`` via
  ``x_steamships_lead_id`` (drives the CRM "Booked Meetings" smart button).
* Remember the visitor's selected client timezone so the calendar view
  renders in the right context.
* Remember the meeting type (Sales Call 30 / Onboarding 60) so we can show
  the correct duration in calendar tiles.

Google Calendar sync fields
---------------------------

``x_google_calendar_*`` fields are populated by the optional Google
Calendar push (``smart_booking.google_calendar``). They are *additive* —
they never replace the native ``calendar.event`` data and they never
break the booking flow when the Google API fails.
"""

from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    x_steamships_booking = fields.Boolean(
        string="Steamships Booking",
        default=False,
        index=True,
        help="True if this event was created from /steamships/booking. "
             "Drives the Smart Booking Calendar / List filters.",
    )
    x_steamships_lead_id = fields.Many2one(
        "crm.lead",
        string="Related CRM Lead",
        index=True,
        help="Optional CRM lead this booking is associated with. "
             "Filled when the customer opened the booking page from a "
             "lead's Booking Link button.",
    )
    x_steamships_client_timezone = fields.Char(
        string="Client Timezone",
        help="IANA timezone name selected by the visitor on the booking "
             "form (e.g. 'Asia/Singapore'). For display only.",
    )
    x_steamships_meeting_type = fields.Selection(
        selection=[
            ("sales_call_30", "Sales Call (30 min)"),
            ("onboarding_60", "Client Onboarding (60 min)"),
        ],
        string="Meeting Type",
        help="Type of meeting chosen on the public booking page.",
    )
    x_steamships_booking_token = fields.Char(
        string="Booking Token",
        index=True,
        help="Opaque token printed on the public form. Used to make the "
             "booking controller idempotent against refresh / double-submit.",
    )

    # ---------------------------------------------------------------
    # Google Calendar sync (optional push, populated after the Odoo
    # ``calendar.event`` has already been created).
    # ---------------------------------------------------------------
    x_google_calendar_event_id = fields.Char(
        string="Google Calendar Event ID",
        readonly=True,
        copy=False,
        index=True,
        groups="base.group_user",
        help="Identifier returned by Google Calendar's events.insert for "
             "the matching event. Empty until the optional Google sync "
             "succeeds.",
    )
    x_google_calendar_synced = fields.Boolean(
        string="Synced to Google Calendar",
        default=False,
        readonly=True,
        copy=False,
        groups="base.group_user",
        help="True once the event has been successfully pushed to the "
             "assigned user's Google Calendar.",
    )
    x_google_calendar_sync_error = fields.Text(
        string="Google Calendar Sync Error",
        readonly=True,
        copy=False,
        groups="base.group_user",
        help="Last error message from the Google Calendar API, if any. "
             "The booking still succeeded — only the Google push failed.",
    )
