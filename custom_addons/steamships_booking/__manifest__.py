# -*- coding: utf-8 -*-
{
    "name": "Steamships Smart Booking",
    "version": "19.0.1.0.0",
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

No Enterprise / Studio / OAuth.
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
        "views/booking_templates.xml",
        "views/crm_lead_views.xml",
        "views/booking_menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
