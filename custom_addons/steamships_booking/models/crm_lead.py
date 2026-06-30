# -*- coding: utf-8 -*-
"""Extend ``crm.lead`` with a button that exposes the public booking URL.

The actual booking flow lives in the public controller
(``steamships_booking.controllers.main``). This model only:

* Computes the absolute public URL.
* Provides a button that opens the URL in the browser.
* As a UX bonus, posts a small chatter note with the link when the
  sales rep uses it (so the team has a record of who shared the link).
"""

import logging

from odoo import _, models

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
    # Button actions
    # ------------------------------------------------------------------
    def action_copy_booking_link(self):
        """Open the public booking URL for the active lead.

        Returns the standard Odoo client action ``ir.actions.act_url``
        so the request opens in a new browser tab. A chatter note is
        posted so internal staff has a record of the share.
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
