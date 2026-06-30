# Smart Booking

Lightweight public booking module for the Steamships Odoo 19 Community prototype.

## What it does

- Public page `/steamships/booking` lets a visitor pick a meeting type, a
  fixed demo slot, and confirm without signing in.
- Creates/finds a `res.partner` by email and books a `calendar.event` in the
  Steamships working timezone (`Pacific/Port_Moresby`).
- If `lead_id` is supplied, posts a chatter note + scheduled activity on the
  related `crm.lead`.
- Adds a **Booking Link** button on the `crm.lead` form to open the public URL.
- Adds a **Steamships → Smart Booking** menu listing booking events.

## Demo slots

The controller exposes 6 demo slots per day, Monday to Friday, PNG local time:

```
09:00, 10:00, 11:00, 14:00, 15:00, 16:00 Pacific/Port_Moresby
```

The browser-side JS converts each slot to the visitor's selected timezone
using `Intl.DateTimeFormat` and marks past slots as disabled.

## Security

- Only an allow-listed set of form fields is read from the public form.
- `crm.lead` reads are restricted to a small public-fields whitelist
  (`name`, `contact_name`, `partner_name`, `email_from`, `function`, `phone`,
  `company_name`).
- `calendar.event` and `res.partner` writes use `sudo()` only on the minimum
  needed `create` calls.
- Chatter / activity post is best-effort: a failure is logged but does not
  break the booking flow.

## Manual acceptance test

1. Open a CRM lead.
2. Click **Booking Link**.
3. Pick `Asia/Singapore` from the timezone selector.
4. Pick a Sales Call slot.
5. Confirm.
6. Verify a `calendar.event` exists.
7. Verify the lead chatter has a "Booking confirmed" note.
8. On the thank-you page, click **Add to Google Calendar**.
