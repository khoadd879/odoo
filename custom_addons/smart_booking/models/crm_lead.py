# -*- coding: utf-8 -*-
"""Extend ``crm.lead`` with Smart Booking integration.

This model adds the "back-link" half of the integration:

* A One2many to the calendar events created via /steamships/booking that
  are tied to this lead (``x_steamships_booking_event_ids``).
* A computed count for the "Booked Meetings" smart button.
* A button action that opens the related events in calendar + list + form
  view.

It also keeps the original "Booking Link" URL helper used by the header
button on the lead form, so sales reps can copy / open the public
booking URL with one click.
"""

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # ------------------------------------------------------------------
    # Public booking URL helpers
    # ------------------------------------------------------------------
    def _get_steamships_booking_url(self):
        """Return the absolute public URL for this lead's booking page."""
        self.ensure_one()
        base = (
            self.env["ir.config_parameter"].sudo().get_param(
                "web.base.url", default="http://localhost:8069")
            or "http://localhost:8069"
        )
        return "%s/steamships/booking?lead_id=%s" % (base.rstrip("/"), self.id)

    # ------------------------------------------------------------------
    # Back-link to calendar events created via /steamships/booking
    # ------------------------------------------------------------------
    x_steamships_booking_event_ids = fields.One2many(
        comodel_name="calendar.event",
        inverse_name="x_steamships_lead_id",
        string="Booked Meetings",
        readonly=True,
    )
    x_steamships_booking_event_count = fields.Integer(
        string="Booked Meetings Count",
        compute="_compute_x_steamships_booking_event_count",
        store=False,
    )

    def _compute_x_steamships_booking_event_count(self):
        for lead in self:
            lead.x_steamships_booking_event_count = (
                len(lead.x_steamships_booking_event_ids))

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------
    def action_copy_booking_link(self):
        """Open the public booking URL for the active lead.

        Returns the standard Odoo client action ``ir.actions.act_url`` so
        the request opens in a new browser tab. A chatter note is posted
        so internal staff has a record of the share.
        """
        self.ensure_one()
        url = self._get_steamships_booking_url()
        try:
            self.message_post(
                body=_(
                    "<b>Booking link shared.</b><br/>"
                    "Public URL: <a href='%s'>%s</a>") % (url, url),
                subject=_("Booking link shared"),
                subtype_xmlid="mail.mt_note",
            )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Failed to post booking-link note on lead %s", self.id)
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_open_booked_meetings(self):
        """Open the calendar events booked for this lead.

        The action targets the same ``calendar.event`` model used by the
        native Calendar app so the user can switch between list / form /
        calendar view with the usual buttons. The domain is restricted
        to ``x_steamships_booking = True`` so we never accidentally show
        unrelated manual events that may also have been linked.
        """
        self.ensure_one()
        action = self.env.ref(
            "smart_booking.action_smart_booking_lead_calendar"
        ).read()[0]
        action["domain"] = [
            ("x_steamships_lead_id", "=", self.id),
        ]
        action["context"] = {
            "default_x_steamships_booking": True,
            "default_x_steamships_lead_id": self.id,
            "search_default_upcoming": 1,
        }
        return action
