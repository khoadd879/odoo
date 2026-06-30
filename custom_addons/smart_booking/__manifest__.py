# -*- coding: utf-8 -*-
{
    "name": "Smart Booking",
    "version": "19.0.2.0.0",
    "summary": "Lightweight public booking flow that creates calendar.events and posts on the CRM lead chatter.",
    "description": """
Steamships Smart Booking
========================

Demo-ready booking flow on Odoo 19 Community.

* Public page ``/steamships/booking`` lets a visitor pick a meeting type,
  pick a fixed demo slot, and confirm without signing in.
* Creates / finds a ``res.partner`` by email and books a ``calendar.event``
  in the Steamships working timezone (Pacific/Port_Moresby).
* If ``lead_id`` is provided, posts a chatter note on the related
  ``crm.lead`` and schedules a follow-up activity.
* Adds a "Booking Link" button on the ``crm.lead`` form to copy the
  public URL.
* Adds a "Steamships -> Smart Booking" menu linking to a filtered
  list of booking events.
* *Optional* Google Calendar push: if the assigned salesperson/admin
  has connected their personal Google Calendar via OAuth 2.0, the same
  meeting is mirrored to their Google Calendar automatically.

No Enterprise / Studio required for the integration. Tokens are stored
as plain ``Char`` for the prototype — encrypt before production.
""",
    "author": "Steamships Prototype Team",
    "website": "https://steamships.com.pg",
    "category": "Website / Booking",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "website",
        "crm",
        "calendar",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        # The CRM lead view must be loaded before our smart button targets it,
        # and the actions / menus reference both, so we keep them in a single
        # data file to avoid cross-file ordering issues.
        "views/crm_lead_views.xml",
        "views/smart_booking_actions.xml",
        "views/booking_menu.xml",
        "views/booking_templates.xml",
        # Google Calendar integration (optional OAuth push). The
        # settings view references ``menu_smart_booking_main``, so it
        # must be loaded after ``smart_booking_actions.xml``.
        "views/google_calendar_settings.xml",
        "views/google_calendar_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
