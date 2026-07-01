# Smart Booking Public Page Redesign Design

Date: 2026-07-01

## Goal

Polish the Smart Booking public booking flow at `/steamships/booking` so it matches the existing clean logistics website style and supports useful guest booking without requiring a CRM lead link.

The work is intentionally scoped: improve UI consistency and guest booking safety while preserving the current Odoo Calendar, CRM lead linkage, Google Calendar push, and thank-you Google Calendar template link behavior.

## Current context

Module: `custom_addons/smart_booking`

Relevant files:

- `custom_addons/smart_booking/views/booking_templates.xml`
- `custom_addons/smart_booking/controllers/main.py`
- `custom_addons/smart_booking/models/calendar_event.py`
- `custom_addons/smart_booking/models/crm_lead.py`

The current booking page uses a dark navy/gold luxury editorial style with custom Google fonts. That visual direction conflicts with the rest of the website, which uses a clean white/light logistics-business style with blue buttons, rounded cards, simple sans-serif typography, and large hero sections.

The current controller already creates `calendar.event` records, can link bookings to a provided `lead_id`, posts lead chatter/activity, stores Smart Booking marker fields, supports idempotency with `x_steamships_booking_token`, and calls the existing best-effort Google Calendar push helper.

## Chosen approach

Use a focused UI refresh plus minimal safe controller changes.

This approach avoids a backend rewrite. It keeps the existing public route and booking flow shape while adding only the behavior needed for public guest bookings without `lead_id`, safer public validation, and fresh upcoming slot generation.

Rejected alternatives:

1. UI-only refresh: lower risk but does not satisfy guest lead creation, honeypot protection, required company validation, or fresh slot generation.
2. Larger booking availability refactor: better long-term architecture, but outside this task and higher risk for Calendar/CRM/Google integrations.

## Page layout and visual direction

The booking page will keep `website.layout` but hide the default Odoo website header/footer for this route only. A custom public mini-header will replace it.

Mini-header:

- Brand text: `Steamships`
- Navigation links: `Home`, `Contact us`, `Booking`
- No public Administrator dropdown
- No placeholder `Your Logo`

Main layout:

- Light background, primarily white and pale gray/blue
- Clean system sans-serif typography
- Large two-column hero on desktop
- Stacked single-column layout on mobile
- Rounded cards
- Light gray borders
- Subtle shadows
- Blue primary accent

Left hero column copy:

- Title: `Book a Steamships Meeting`
- Subtitle: `Choose a time that works in your timezone.`
- Paragraph: `Pick a meeting slot online. We’ll save it to Odoo Calendar and link it to your CRM record when available.`

Feature cards:

1. `Timezone aware` — `Slots are shown in your selected timezone.`
2. `CRM connected` — `Bookings from a lead are saved back to the customer record.`
3. `Calendar ready` — `Meetings are saved into Odoo Calendar and can sync to Google Calendar.`

Right column:

- White booking form card
- Meeting type selector
- Your name
- Work email
- Company
- Timezone selector and Detect button
- Slot picker
- Notes
- Hidden honeypot field
- Blue Confirm Booking button

The redesign will remove dark full-page navy styling, gold luxury accents, serif title styling, decorative stamp elements, grain/grid/orb backgrounds, and oversized editorial typography.

## Form components

### Booking card

The form card will use:

- White background
- Rounded corners
- Soft shadow
- Light border
- Dark neutral heading text
- Gray body/label text
- Blue focus and selected states
- Blue primary submit button

### Meeting type cards

The two meeting types remain:

- `Sales Call (30 min)`
- `Client Onboarding (60 min)`

Selected state:

- Blue border
- Pale blue background
- Clear selected indicator

Unselected state:

- White background
- Light gray border

### Slot picker

Slots are grouped by upcoming business day. Example:

- Monday, 06 Jul
  - 09:00
  - 10:00
  - 11:00
  - 14:00
  - 15:00
  - 16:00

Each slot button shows:

- Main time in the selected visitor timezone
- Secondary label in PNG base timezone, e.g. `PNG 09:00`

Available slots must look clickable:

- White background
- Gray border
- Pointer cursor
- Blue hover state

Selected slots must be obvious:

- Solid blue or strongly highlighted blue border/background
- White or high-contrast text

Disabled or strikethrough styling is only used when a slot is actually unavailable or past. Normal available slots must not appear disabled.

## Slot generation and validation

The server will generate slots for the next 5 business days from the current date in PNG time (`Pacific/Port_Moresby`, UTC+10). Standard demo hours remain:

- 09:00
- 10:00
- 11:00
- 14:00
- 15:00
- 16:00

If today is a business day, only future slots later than the current PNG time are included. Past slots are not shown as available.

The submitted slot key will represent an exact PNG-local date and time, not only a weekday/hour demo pattern. Server-side validation will only accept a submitted slot if it matches the currently generated upcoming slots.

The client-side JavaScript will update visible slot labels when the timezone changes, using the server-provided UTC instant for each slot. The hidden submitted value remains the server-recognized slot key.

## Guest booking behavior

The public booking route remains:

```python
@http.route("/steamships/booking", auth="public", website=True, type="http")
```

Guests can open the page and submit:

- name
- email
- company
- timezone
- meeting type
- slot
- notes

The submit flow remains the same overall shape:

1. Read only whitelisted public form fields.
2. Validate required values, email, timezone, meeting type, honeypot, and slot.
3. Find or create a `res.partner` by submitted email.
4. Resolve a provided CRM lead or create a website-origin lead.
5. Resolve salesperson using the existing salesperson fallback helper.
6. Create `calendar.event` with existing Smart Booking marker fields.
7. Push to Google Calendar best-effort using the existing helper.
8. Post booking chatter/activity on the related lead.
9. Redirect to the thank-you page.

### When `lead_id` exists and is valid

The controller will:

- Parse `lead_id` as an integer.
- Search only for that exact ID with `limit=1`.
- Use only safe public prefill fields.
- Link the created event to the CRM lead through `x_steamships_lead_id`.
- Post the booking note/activity to that lead.

### When `lead_id` is missing or invalid

The controller will create a new `crm.lead` / opportunity for the website booking.

Lead values:

- `name`: `Website Booking - <Company>`
- `contact_name`: submitted name
- `email_from`: submitted email
- `partner_id`: found or created partner
- `description`: booking notes plus selected meeting details
- `user_id`: resolved fallback salesperson/admin

The event will link to this new lead through `x_steamships_lead_id`, and the same booking chatter/activity will be posted to the new lead.

## Public security boundaries

The public page must not expose internal CRM fields.

Safe lead prefill fields only:

- company name
- contact name
- email
- phone if already part of the existing safe field list, though the redesigned form does not need to show phone
- lead ID only as a hidden continuation token for a direct booking link

The public page must not expose:

- internal notes
- expected revenue
- salesperson notes
- attachments
- activities
- chatter
- arbitrary lead search

The controller must avoid public CRM search behavior. It may use `sudo()` only for controlled record operations needed by this public flow, such as exact-ID lead read, partner find/create, lead create, event create, and chatter post on the resolved lead.

No `sudo().search([])` will be added for CRM leads.

Spam and validation controls:

- Hidden honeypot field
- If honeypot is filled, redirect neutrally without creating records or revealing internal validation details
- Server-side basic email validation
- Required `name`, `email`, `company`, `slot`, `timezone`, and `meeting_type`
- Server-side slot validation against generated upcoming slot keys

## Thank-you page

The thank-you page will use the same light website style as the booking page.

Content:

- Success card
- Title: `Your meeting is booked`
- Meeting type
- Date/time in selected timezone
- PNG time
- Email
- Company

Actions:

- `Add to Google Calendar`
- `Back to Website`

The existing Google Calendar template URL behavior stays. No new OAuth work is included.

To show email and company on the thank-you page without exposing broad internals, the controller will derive a small safe summary from the public booking lines already written to the event description, such as `Email:` and `Company:`. The page will not display the full event description or CRM lead internals.

## Integration preservation

The implementation must preserve:

- `calendar.event` creation
- `x_steamships_booking = True`
- `x_steamships_lead_id`
- `x_steamships_client_timezone`
- `x_steamships_meeting_type`
- `x_steamships_booking_token`
- Partner attendees on the calendar event
- CRM chatter post
- Follow-up activity scheduling
- Smart Booking filtered calendar/list behavior
- Best-effort Google Calendar push via `smart_booking.google_calendar.push_event_to_google`
- Thank-you page Google Calendar template URL

Google Calendar push remains best-effort and must not block the booking flow if it fails.

## Error handling

Validation errors should prevent record creation and surface clear feedback where practical. The existing form already performs client-side validation; server-side validation remains authoritative.

For public spam/honeypot submissions, the implementation will redirect neutrally without creating records and without exposing internal validation details that help spam automation.

Google Calendar push and chatter/activity posting remain best-effort. Failures are logged and do not undo a successful calendar event creation.

## Verification plan

After implementation:

1. Run:

   ```bash
   ./scripts/update-module.sh smart_booking
   ```

2. Because `controllers/main.py` will change, restart only Odoo:

   ```bash
   docker compose restart odoo
   ```

3. Do not restart the database, remove volumes, or run init-db.

Manual acceptance tests:

### Test A: guest booking without `lead_id`

- Open `http://localhost:8069/steamships/booking`.
- Confirm the page matches the light logistics website style.
- Submit a booking as a guest.
- Confirm a `calendar.event` is created.
- Confirm a new CRM lead/opportunity is created.
- Confirm the event is linked to the created CRM lead.

### Test B: booking with `lead_id`

- Open a CRM lead.
- Click Booking Link.
- Submit a booking.
- Confirm a `calendar.event` is created.
- Confirm the CRM lead chatter receives the booking note.
- Confirm the event appears under Smart Booking.
- If the salesperson has Google Calendar connected, confirm Google sync still works.

### Test C: UI behavior

- Confirm available slots are not all strikethrough.
- Confirm selected slot is clearly highlighted.
- Confirm timezone changes update slot labels.
- Confirm mobile layout is readable.

## Out of scope

- Real calendar conflict checking beyond rejecting stale/past generated slots
- New OAuth or Google Calendar authorization work
- Rewriting the booking backend flow
- Changing Smart Booking model fields
- Public CRM lead search
- Broad website theme redesign outside the booking/thank-you pages
