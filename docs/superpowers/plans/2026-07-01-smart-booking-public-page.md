# Smart Booking Public Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/steamships/booking` to match the clean Steamships/Odoo Website style while preserving Calendar, CRM, and Google Calendar integrations and allowing useful guest bookings without `lead_id`.

**Architecture:** Keep the existing public controller flow, but add small pure helpers for upcoming business-day slots, server-side slot validation, website-origin lead creation, and thank-you summary extraction. Replace the inline dark luxury booking/thank-you QWeb with a light, blue-accented public mini-header, hero, form card, slot picker, and success card.

**Tech Stack:** Odoo 19 QWeb templates, Odoo HTTP controllers, `crm.lead`, `res.partner`, `calendar.event`, existing Smart Booking model fields, browser `Intl.DateTimeFormat`, Docker Compose for Odoo restart.

---

## Execution notes

- Do **not** commit unless the user explicitly asks. The plan omits commit steps because the active Claude Code instructions say commits/pushes require explicit user request.
- Do **not** restart the database.
- Do **not** remove Docker volumes.
- Do **not** run init-db.
- Preserve existing modified files outside this task; the working tree already has user changes.

## File structure

Modify these files only unless implementation discovers a hard blocker:

- `custom_addons/smart_booking/controllers/main.py`
  - Owns public GET/POST/thanks behavior.
  - Add helper constants and functions for slot generation, validation, website lead descriptions, and safe thank-you summaries.
  - Keep the existing `calendar.event` creation and Google Calendar push sequence.

- `custom_addons/smart_booking/views/booking_templates.xml`
  - Owns the public booking and thank-you QWeb markup, inline route-scoped CSS, and inline client-side slot/timezone behavior.
  - Replace dark/gold style with light website style.
  - Add honeypot input and update slot rendering to consume exact server slot metadata.

No new model fields are required. No static CSS/JS files exist under `custom_addons/smart_booking/static/src`, so keep the route-scoped inline CSS/JS pattern already used by the template.

---

### Task 1: Add upcoming-slot helpers and remove stale weekday-only slot keys

**Files:**
- Modify: `custom_addons/smart_booking/controllers/main.py:31-171`

- [ ] **Step 1: Add imports and constants**

In `custom_addons/smart_booking/controllers/main.py`, add `re` to the imports and define shared slot constants near the existing timezone constants.

```python
import datetime
import logging
import re
import secrets
import urllib.parse
```

Add these constants after `PUBLIC_TZ_WHITELIST`:

```python
SLOT_HOURS = ((9, 0), (10, 0), (11, 0), (14, 0), (15, 0), (16, 0))
BUSINESS_SLOT_DAYS = 5
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
```

- [ ] **Step 2: Replace `_build_demo_slots()` with exact upcoming business-day slot generation**

Replace the existing `_build_demo_slots()` function at `custom_addons/smart_booking/controllers/main.py:124-136` with this code:

```python
def _slot_key(slot_png_local):
    """Return the public form key for an exact PNG-local slot."""
    return slot_png_local.strftime("%Y-%m-%d_%H_%M")


def _slot_payload(slot_png_local):
    """Build one public slot payload from a PNG-local naive datetime."""
    slot_utc_naive = _png_local_to_utc(slot_png_local).replace(tzinfo=None)
    return {
        "key": _slot_key(slot_png_local),
        "date": slot_png_local.strftime("%Y-%m-%d"),
        "day_label": slot_png_local.strftime("%A, %d %b"),
        "weekday_label": slot_png_local.strftime("%a"),
        "hour": slot_png_local.hour,
        "minute": slot_png_local.minute,
        "label_png": "PNG %02d:%02d" % (slot_png_local.hour, slot_png_local.minute),
        "utc_iso": slot_utc_naive.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _build_upcoming_slot_days(now_utc=None, business_days=BUSINESS_SLOT_DAYS):
    """Return grouped upcoming business slots from the current PNG time.

    The public page should never show stale demo dates. Slots are generated
    for the next `business_days` Monday-Friday dates. If today is a business
    day, only future slots later than the current PNG time are included.
    """
    now_utc = now_utc or datetime.datetime.utcnow()
    now_png = (now_utc + datetime.timedelta(hours=PNG_TZ_OFFSET_HOURS)).replace(
        tzinfo=None)
    cursor = now_png.replace(hour=0, minute=0, second=0, microsecond=0)
    days = []

    while len(days) < business_days:
        if cursor.weekday() < 5:
            slots = []
            for hour, minute in SLOT_HOURS:
                slot_png_local = cursor.replace(
                    hour=hour, minute=minute, second=0, microsecond=0)
                if slot_png_local > now_png:
                    slots.append(_slot_payload(slot_png_local))
            if slots:
                days.append({
                    "date": cursor.strftime("%Y-%m-%d"),
                    "day_label": cursor.strftime("%A, %d %b"),
                    "slots": slots,
                })
        cursor += datetime.timedelta(days=1)

    return days


def _flatten_slot_days(slot_days):
    """Return a flat slot list from grouped slot days."""
    return [slot for day in slot_days for slot in day.get("slots", [])]
```

- [ ] **Step 3: Replace `_resolve_slot_iso()` with exact-date validation**

Replace the current `_resolve_slot_iso()` at `custom_addons/smart_booking/controllers/main.py:139-171` with this implementation:

```python
def _resolve_slot_iso(slot_key, available_slot_days=None):
    """Resolve an exact public slot key to PNG-local and UTC datetimes.

    Valid keys look like `YYYY-MM-DD_HH_MM`. The key must match one of the
    currently generated upcoming slots, which prevents stale/past form posts.
    """
    available_slot_days = available_slot_days or _build_upcoming_slot_days()
    valid_slots = {
        slot["key"]: slot
        for slot in _flatten_slot_days(available_slot_days)
    }
    if slot_key not in valid_slots:
        raise ValidationError(_("Please choose an available future time slot."))

    try:
        date_str, hh_str, mm_str = slot_key.rsplit("_", 2)
        year_str, month_str, day_str = date_str.split("-")
        slot_png_local = datetime.datetime(
            int(year_str), int(month_str), int(day_str), int(hh_str), int(mm_str))
    except (TypeError, ValueError):
        raise ValidationError(_("Invalid slot selection."))

    slot_utc_naive = _png_local_to_utc(slot_png_local)
    return slot_png_local, slot_utc_naive.replace(tzinfo=None)
```

- [ ] **Step 4: Update the booking page render context**

In `booking_page()`, replace the current render value:

```python
"slots": _build_demo_slots(),
```

with:

```python
"slot_days": _build_upcoming_slot_days(),
```

- [ ] **Step 5: Update submit-time slot resolution to use the same generated slots**

In `booking_submit()`, replace:

```python
slot_png_local, slot_utc_naive = _resolve_slot_iso(slot_key)
```

with:

```python
available_slot_days = _build_upcoming_slot_days()
slot_png_local, slot_utc_naive = _resolve_slot_iso(
    slot_key, available_slot_days=available_slot_days)
```

- [ ] **Step 6: Run Python syntax check**

Run:

```bash
python -m py_compile custom_addons/smart_booking/controllers/main.py
```

Expected: command exits with status 0 and prints no output.

---

### Task 2: Add safe guest lead creation, honeypot handling, and stricter submit validation

**Files:**
- Modify: `custom_addons/smart_booking/controllers/main.py:174-480`

- [ ] **Step 1: Tighten fallback salesperson search to avoid `sudo().search([])`**

In `_resolve_salesperson_user()`, replace the final fallback block:

```python
# Fallbacks: try admin, then any user (e.g. demo data).
admin_ref = request_env.ref("base.user_admin", raise_if_not_found=False)
if admin_ref and admin_ref.sudo().exists():
    return admin_ref.sudo()
user = UserSudo.with_context(active_test=False).search([], limit=1)
if user:
    return user
raise ValidationError(_(
    "No sales user found to assign the booking to. Please contact "
    "your administrator."))
```

with:

```python
# Fallbacks: try admin, then a non-share internal user. Avoid a blank
# sudo().search([]) in this public flow.
admin_ref = request_env.ref("base.user_admin", raise_if_not_found=False)
if admin_ref and admin_ref.sudo().exists():
    return admin_ref.sudo()
user = UserSudo.with_context(active_test=False).search(
    [("share", "=", False)], limit=1)
if user:
    return user
raise ValidationError(_(
    "No sales user found to assign the booking to. Please contact "
    "your administrator."))
```

- [ ] **Step 2: Add helper functions for website-origin lead content and safe summary extraction**

Add these helpers after `_resolve_salesperson_user()` and before `class SteamshipsBookingController`:

```python
def _build_website_lead_description(meeting_label, name, email, company,
                                    timezone_name, slot_png_local,
                                    duration_minutes, notes):
    """Return a safe CRM lead description for a public website booking."""
    png_stop = slot_png_local + datetime.timedelta(minutes=duration_minutes)
    lines = [
        "Website booking submitted from /steamships/booking.",
        "",
        "Meeting type: %s" % meeting_label,
        "Name: %s" % name,
        "Email: %s" % email,
        "Company: %s" % company,
        "Client timezone: %s" % timezone_name,
        "PNG time: %s – %s" % (
            slot_png_local.strftime("%A, %d %b %Y %H:%M"),
            png_stop.strftime("%H:%M"),
        ),
        "",
        "Notes: %s" % (notes or "—"),
    ]
    return "\n".join(lines)


def _extract_public_booking_summary(description):
    """Extract public booking fields from the event description.

    The thank-you page can show these values because they came from the
    visitor's own submitted public form fields. It must not render the full
    description or any CRM internals.
    """
    summary = {"email": "", "company": ""}
    for line in (description or "").splitlines():
        if line.startswith("Email: "):
            summary["email"] = line.partition(": ")[2]
        elif line.startswith("Company: "):
            summary["company"] = line.partition(": ")[2]
    return summary
```

- [ ] **Step 3: Read and enforce the honeypot field**

In `booking_submit()`, after reading `booking_token`, add:

```python
website_url = (post.get("website_url") or "").strip()
```

Immediately after field reads and before normal validation, add:

```python
# Honeypot: bots often fill hidden URL/company fields. Do not create any
# records and do not reveal validation details.
if website_url:
    return http.request.redirect("/steamships/booking/thanks")
```

- [ ] **Step 4: Strengthen required-field and email validation**

Replace this validation block:

```python
if meeting_type not in DURATION_MINUTES:
    raise ValidationError(_("Please pick a valid meeting type."))
if not name or not email:
    raise ValidationError(_("Name and email are required."))
if timezone_name not in PUBLIC_TZ_WHITELIST:
    raise ValidationError(_("Please pick a supported timezone."))
if "@" not in email:
    raise ValidationError(_("Please provide a valid email."))
```

with:

```python
if meeting_type not in DURATION_MINUTES:
    raise ValidationError(_("Please pick a valid meeting type."))
if not name:
    raise ValidationError(_("Name is required."))
if not email or not EMAIL_RE.match(email):
    raise ValidationError(_("Please provide a valid work email."))
if not company:
    raise ValidationError(_("Company is required."))
if timezone_name not in PUBLIC_TZ_WHITELIST:
    raise ValidationError(_("Please pick a supported timezone."))
if not slot_key:
    raise ValidationError(_("Please choose a time slot."))
```

- [ ] **Step 5: Create a website-origin CRM lead when no valid lead was supplied**

In `booking_submit()`, keep the existing exact-ID lead lookup, then replace the salesperson resolution comment/block:

```python
# Resolve the salesperson user (lead.user_id -> request.env.user -> fallback).
salesperson_user = _resolve_salesperson_user(
    lead, http.request.env)
```

with this larger block:

```python
# Resolve the salesperson user (lead.user_id -> request.env.user -> fallback).
salesperson_user = _resolve_salesperson_user(lead, http.request.env)
meeting_label = MEETING_TYPE_LABELS[meeting_type]

# Public bookings without a valid lead_id still become useful CRM work.
if not lead:
    Lead = http.request.env["crm.lead"].sudo()
    lead_name = "Website Booking - %s" % company
    lead = Lead.create({
        "name": lead_name,
        "contact_name": name,
        "email_from": email,
        "partner_id": partner.id,
        "description": _build_website_lead_description(
            meeting_label, name, email, company, timezone_name,
            slot_png_local, duration_minutes, notes),
        "user_id": salesperson_user.id,
    })
    lead_id = lead.id
```

- [ ] **Step 6: Remove duplicate `meeting_label` assignment**

A few lines below, the current code has:

```python
meeting_label = MEETING_TYPE_LABELS[meeting_type]
event_name = "%s — %s" % (
```

Remove the duplicate `meeting_label = ...` line because Step 5 now assigns it before optional website lead creation. Leave `event_name` unchanged.

- [ ] **Step 7: Keep the event linked to either existing or newly created lead**

Confirm `event_vals` still contains:

```python
"x_steamships_lead_id": lead.id if lead else False,
```

After Step 5, `lead` should always be set for legitimate submissions, so this preserves CRM linkage for both lead-linked and guest bookings.

- [ ] **Step 8: Run Python syntax check**

Run:

```bash
python -m py_compile custom_addons/smart_booking/controllers/main.py
```

Expected: command exits with status 0 and prints no output.

---

### Task 3: Polish thank-you data preparation without exposing CRM internals

**Files:**
- Modify: `custom_addons/smart_booking/controllers/main.py:491-556`

- [ ] **Step 1: Add safe thank-you summary fields**

Inside `booking_thanks()`, after `event = events[0]`, add these assignments after the existing date label calculations and before `event["google_url"] = ...`:

```python
meeting_type_key = event.get("x_steamships_meeting_type")
event["meeting_label"] = MEETING_TYPE_LABELS.get(
    meeting_type_key, event.get("name") or "Steamships Meeting")
event["public_summary"] = _extract_public_booking_summary(
    event.get("description"))
```

Place it near the existing `tz_label` code so the template receives:

- `event['meeting_label']`
- `event['public_summary']['email']`
- `event['public_summary']['company']`

- [ ] **Step 2: Keep the Google Calendar template URL unchanged**

Confirm the code still ends the event preparation with:

```python
event["google_url"] = _google_calendar_url(event_obj, tz_label)
```

Do not add OAuth or replace the template URL.

- [ ] **Step 3: Run Python syntax check**

Run:

```bash
python -m py_compile custom_addons/smart_booking/controllers/main.py
```

Expected: command exits with status 0 and prints no output.

---

### Task 4: Redesign the booking page QWeb markup, CSS, and slot JavaScript

**Files:**
- Modify: `custom_addons/smart_booking/views/booking_templates.xml:4-1161`

- [ ] **Step 1: Remove Google font dependencies from the booking page head**

In the `booking_page` template, replace the current `head` block that preconnects Google fonts with:

```xml
<t t-set="head">
    <meta name="robots" content="noindex"/>
</t>
```

- [ ] **Step 2: Replace the booking page chrome and hero markup with light website-style structure**

Inside `<div class="ssbk-page">`, remove the dark ambient background elements:

```xml
<div class="ssbk-bg-grain" aria-hidden="true"></div>
<div class="ssbk-bg-grid" aria-hidden="true"></div>
<div class="ssbk-bg-orb ssbk-bg-orb-1" aria-hidden="true"></div>
<div class="ssbk-bg-orb ssbk-bg-orb-2" aria-hidden="true"></div>
```

Replace the existing `<main class="ssbk-shell"> ... </main>` content with this structure. Keep the existing form action, CSRF token, `lead_id`, and `booking_token` behavior.

```xml
<header class="ssbk-site-header">
    <a class="ssbk-logo" href="/" aria-label="Steamships home">Steamships</a>
    <nav class="ssbk-nav" aria-label="Booking navigation">
        <a href="/">Home</a>
        <a href="/contactus">Contact us</a>
        <a class="is-active" href="/steamships/booking">Booking</a>
    </nav>
</header>

<main class="ssbk-shell">
    <section class="ssbk-intro">
        <p class="ssbk-eyebrow">Steamships Smart Booking</p>
        <h1 class="ssbk-title">Book a Steamships Meeting</h1>
        <p class="ssbk-subtitle">Choose a time that works in your timezone.</p>
        <p class="ssbk-copy">
            Pick a meeting slot online. We’ll save it to Odoo Calendar and link it
            to your CRM record when available.
        </p>

        <div class="ssbk-feature-grid">
            <article class="ssbk-feature-card">
                <span class="ssbk-feature-icon">🌐</span>
                <h3>Timezone aware</h3>
                <p>Slots are shown in your selected timezone.</p>
            </article>
            <article class="ssbk-feature-card">
                <span class="ssbk-feature-icon">🔗</span>
                <h3>CRM connected</h3>
                <p>Bookings from a lead are saved back to the customer record.</p>
            </article>
            <article class="ssbk-feature-card">
                <span class="ssbk-feature-icon">📅</span>
                <h3>Calendar ready</h3>
                <p>Meetings are saved into Odoo Calendar and can sync to Google Calendar.</p>
            </article>
        </div>
    </section>

    <section class="ssbk-booking" aria-labelledby="ssbk-form-heading">
        <div class="ssbk-card">
            <div class="ssbk-card-head">
                <p class="ssbk-card-tag">Public booking</p>
                <h2 id="ssbk-form-heading" class="ssbk-card-title">Choose your meeting details</h2>
                <p class="ssbk-card-sub">All fields except notes are required.</p>
            </div>

            <t t-if="prefilled.get('lead_id')">
                <div class="ssbk-banner">
                    Booking is linked to your CRM record. Please confirm your details.
                </div>
            </t>

            <form id="ssbk-form" class="ssbk-form"
                  t-attf-action="/steamships/booking/submit" method="post"
                  novalidate="novalidate">
                <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
                <input type="hidden" name="lead_id" t-att-value="prefilled.get('lead_id', '')"/>
                <input type="hidden" name="booking_token" t-att-value="booking_token"/>

                <div class="ssbk-honeypot" aria-hidden="true">
                    <label for="ssbk-website-url">Website</label>
                    <input id="ssbk-website-url" name="website_url" type="text" tabindex="-1" autocomplete="off"/>
                </div>

                <!-- Keep the existing fieldsets for meeting type, contact details,
                     timezone, slots, notes, submit, and footer, but update their
                     classes/content in the following steps. -->
            </form>
        </div>
    </section>
</main>
```

Then move the existing fieldsets from the current form into the new form where the comment sits, applying Steps 3-6 below.

- [ ] **Step 3: Update meeting type cards to blue selected states**

Keep the existing `t-foreach="meeting_types.items()"` loop, but simplify the card text so each card displays only the requested label and duration/subtitle. The selected state is controlled by CSS on `input:checked + .ssbk-mtype-card`.

Use this card body inside each `<label class="ssbk-mtype">`:

```xml
<input type="radio" name="meeting_type"
       t-att-value="mt[0]"
       required="required"
       t-att-checked="'checked' if mt[0] == 'sales_call_30' else None"/>
<span class="ssbk-mtype-card">
    <span class="ssbk-mtype-title" t-esc="mt[1]"/>
    <span class="ssbk-mtype-sub">
        <t t-if="mt[0] == 'sales_call_30'">Introductory sales conversation</t>
        <t t-if="mt[0] == 'onboarding_60'">Client onboarding and kickoff</t>
    </span>
</span>
```

- [ ] **Step 4: Render slots from `slot_days` instead of stale `slots`**

Replace the current slot day rendering block under `<div class="ssbk-slots" id="ssbk-slots">` with:

```xml
<t t-foreach="slot_days" t-as="day">
    <div class="ssbk-day">
        <div class="ssbk-day-label">
            <span class="ssbk-day-name" t-esc="day['day_label']"/>
        </div>
        <div class="ssbk-day-slots">
            <t t-foreach="day['slots']" t-as="slot">
                <button type="button"
                        class="ssbk-slot"
                        t-att-data-slot-key="slot['key']"
                        t-att-data-utc="slot['utc_iso']"
                        t-att-data-label-png="slot['label_png']">
                    <span class="ssbk-slot-local">--:--</span>
                    <span class="ssbk-slot-png" t-esc="slot['label_png']"/>
                </button>
            </t>
        </div>
    </div>
</t>
```

Keep the hidden slot input:

```xml
<input type="hidden" name="slot" id="ssbk-slot-input" required="required"/>
```

- [ ] **Step 5: Replace booking page CSS with the light theme**

Replace the booking page `<style>` block with CSS that keeps the same `ssbk-*` class names and includes these required rules:

```css
body.o_steamships_booking_page header,
body.o_steamships_booking_page nav.o_navbar,
body.o_steamships_booking_page footer,
body.o_steamships_booking_page #top,
body.o_steamships_booking_page #wrap > footer,
body.o_steamships_booking_page .o_footer,
body.o_steamships_booking_page .o_wwebsite_footer { display: none !important; }
body.o_steamships_booking_page #wrap { padding-top: 0 !important; padding-bottom: 0 !important; }
body.o_steamships_booking_page main, body.o_steamships_booking_page #main { padding: 0 !important; }

body.o_steamships_booking_page {
    background: #f6f9fc;
    color: #172033;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
}
.ssbk-page {
    min-height: 100vh;
    background:
        radial-gradient(circle at 12% 0%, rgba(32, 116, 214, .10), transparent 32rem),
        linear-gradient(180deg, #ffffff 0%, #f6f9fc 62%, #eef4fb 100%);
}
.ssbk-site-header {
    max-width: 1180px;
    margin: 0 auto;
    padding: 22px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 18px;
}
.ssbk-logo { color: #1259b2; font-weight: 800; font-size: 1.25rem; text-decoration: none; }
.ssbk-nav { display: flex; gap: 18px; align-items: center; }
.ssbk-nav a { color: #536172; text-decoration: none; font-weight: 600; font-size: .94rem; }
.ssbk-nav a:hover, .ssbk-nav a.is-active { color: #1266d6; }
.ssbk-shell {
    max-width: 1180px;
    margin: 0 auto;
    padding: 48px 24px 72px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(420px, .9fr);
    gap: 48px;
    align-items: start;
}
.ssbk-eyebrow { color: #1266d6; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; font-size: .78rem; margin: 0 0 14px; }
.ssbk-title { color: #10233f; font-size: clamp(2.4rem, 5vw, 4.2rem); line-height: 1.02; letter-spacing: -.04em; margin: 0 0 14px; font-weight: 800; }
.ssbk-subtitle { color: #243b5a; font-size: 1.35rem; margin: 0 0 14px; font-weight: 650; }
.ssbk-copy { color: #5d6b7d; line-height: 1.7; max-width: 42rem; margin: 0 0 28px; }
.ssbk-feature-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.ssbk-feature-card { background: #fff; border: 1px solid #dbe5f0; border-radius: 18px; padding: 18px; box-shadow: 0 14px 35px rgba(20, 54, 96, .07); }
.ssbk-feature-icon { display: inline-flex; margin-bottom: 10px; }
.ssbk-feature-card h3 { color: #10233f; font-size: 1rem; margin: 0 0 6px; font-weight: 750; }
.ssbk-feature-card p { color: #637184; margin: 0; line-height: 1.5; font-size: .92rem; }
.ssbk-card { background: #fff; border: 1px solid #dbe5f0; border-radius: 24px; padding: 30px; box-shadow: 0 24px 60px rgba(20, 54, 96, .14); }
.ssbk-card-tag { color: #1266d6; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; margin: 0 0 8px; }
.ssbk-card-title { color: #10233f; margin: 0 0 8px; font-size: 1.55rem; font-weight: 800; }
.ssbk-card-sub { color: #637184; margin: 0; }
.ssbk-banner { background: #eef7ff; border: 1px solid #bfdbfe; color: #174ea6; border-radius: 14px; padding: 12px 14px; margin: 20px 0; font-size: .92rem; }
.ssbk-form { display: flex; flex-direction: column; gap: 24px; margin-top: 24px; }
.ssbk-honeypot { position: absolute !important; left: -10000px !important; width: 1px !important; height: 1px !important; overflow: hidden !important; }
.ssbk-field { border: 0; padding: 0; margin: 0; min-width: 0; }
.ssbk-label { display: block; color: #243b5a; font-weight: 750; font-size: .88rem; margin: 0 0 10px; }
.ssbk-label-optional { color: #8a98aa; font-weight: 500; }
.ssbk-sublabel { display: block; color: #34445a; font-weight: 650; font-size: .86rem; margin: 0 0 6px; }
.ssbk-row { display: grid; gap: 14px; }
.ssbk-row-2 { grid-template-columns: 1fr 1fr; }
.ssbk-input, .ssbk-select, textarea.ssbk-input { width: 100%; border: 1px solid #d2dce8; border-radius: 12px; padding: 12px 14px; color: #172033; background: #fff; font: inherit; transition: border-color .16s ease, box-shadow .16s ease; }
.ssbk-input:focus, .ssbk-select:focus, textarea.ssbk-input:focus { outline: 0; border-color: #1266d6; box-shadow: 0 0 0 4px rgba(18, 102, 214, .14); }
.ssbk-input.is-invalid, .ssbk-select.is-invalid { border-color: #dc2626; box-shadow: 0 0 0 4px rgba(220, 38, 38, .10); }
.ssbk-field-error { display: block; margin-top: 6px; color: #b91c1c; font-size: .82rem; font-weight: 600; }
.ssbk-meeting-types { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ssbk-mtype { cursor: pointer; position: relative; }
.ssbk-mtype input { position: absolute; opacity: 0; pointer-events: none; }
.ssbk-mtype-card { display: block; height: 100%; border: 1.5px solid #dbe5f0; border-radius: 16px; padding: 16px; background: #fff; transition: border-color .16s ease, background .16s ease, box-shadow .16s ease; }
.ssbk-mtype:hover .ssbk-mtype-card { border-color: #7bb3f3; background: #f8fbff; }
.ssbk-mtype input:checked + .ssbk-mtype-card { border-color: #1266d6; background: #eef7ff; box-shadow: 0 0 0 4px rgba(18, 102, 214, .12); }
.ssbk-mtype-title { display: block; color: #10233f; font-weight: 800; margin-bottom: 4px; }
.ssbk-mtype-sub { display: block; color: #637184; font-size: .84rem; line-height: 1.4; }
.ssbk-tz-row { display: flex; gap: 10px; }
.ssbk-select { flex: 1; }
.ssbk-tz-btn { border: 1px solid #d2dce8; background: #fff; color: #1266d6; border-radius: 12px; padding: 0 14px; font-weight: 750; cursor: pointer; }
.ssbk-tz-btn:hover { border-color: #1266d6; background: #f8fbff; }
.ssbk-tz-hint, .ssbk-mini-note { color: #637184; font-size: .84rem; margin: 6px 0 10px; }
.ssbk-slots { border: 1px solid #dbe5f0; border-radius: 18px; padding: 8px; background: #f8fbff; }
.ssbk-day { display: grid; grid-template-columns: 130px 1fr; gap: 12px; padding: 14px 10px; border-bottom: 1px solid #e4edf7; }
.ssbk-day:last-child { border-bottom: 0; }
.ssbk-day-name { color: #243b5a; font-weight: 800; font-size: .94rem; }
.ssbk-day-slots { display: flex; flex-wrap: wrap; gap: 8px; }
.ssbk-slot { min-width: 86px; border: 1px solid #ccd8e6; background: #fff; color: #172033; border-radius: 12px; padding: 10px 12px; cursor: pointer; text-align: left; display: flex; flex-direction: column; gap: 2px; transition: border-color .16s ease, background .16s ease, color .16s ease, box-shadow .16s ease, transform .12s ease; }
.ssbk-slot:hover:not(:disabled) { border-color: #1266d6; background: #f0f7ff; transform: translateY(-1px); }
.ssbk-slot.is-selected { background: #1266d6; border-color: #1266d6; color: #fff; box-shadow: 0 10px 22px rgba(18, 102, 214, .24); }
.ssbk-slot-local { font-weight: 850; font-size: .98rem; }
.ssbk-slot-png { color: #6d7c90; font-size: .72rem; font-weight: 650; }
.ssbk-slot.is-selected .ssbk-slot-png { color: rgba(255,255,255,.82); }
.ssbk-slot.is-past, .ssbk-slot:disabled { opacity: .45; cursor: not-allowed; text-decoration: line-through; background: #eef2f6; }
.ssbk-submit { width: 100%; border: 0; border-radius: 14px; padding: 15px 20px; background: #1266d6; color: #fff; font-weight: 850; font-size: 1rem; cursor: pointer; box-shadow: 0 14px 28px rgba(18, 102, 214, .22); transition: background .16s ease, transform .12s ease, box-shadow .16s ease; }
.ssbk-submit:hover { background: #0d57bc; transform: translateY(-1px); box-shadow: 0 18px 34px rgba(18, 102, 214, .28); }
.ssbk-submit:disabled { background: #94a3b8; cursor: not-allowed; box-shadow: none; transform: none; }
.ssbk-footer { color: #7a8798; font-size: .78rem; text-align: center; margin: 0; line-height: 1.5; }
@media (max-width: 980px) {
    .ssbk-shell { grid-template-columns: 1fr; padding-top: 26px; }
    .ssbk-feature-grid { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
    .ssbk-site-header { flex-direction: column; align-items: flex-start; }
    .ssbk-nav { gap: 12px; flex-wrap: wrap; }
    .ssbk-card { padding: 22px; border-radius: 18px; }
    .ssbk-row-2, .ssbk-meeting-types, .ssbk-day { grid-template-columns: 1fr; }
    .ssbk-tz-row { flex-direction: column; }
    .ssbk-title { font-size: 2.35rem; }
}
```

- [ ] **Step 6: Replace booking page JavaScript slot conversion with UTC-based labels**

In the booking page `<script>`, keep the current validation structure but replace `getSlotInTz()` and `refreshSlots()` with UTC-based logic:

```javascript
function formatSlotTime(utcIso, tz) {
    try {
        var date = new Date(utcIso);
        if (isNaN(date.getTime())) { return null; }
        var dtf = new Intl.DateTimeFormat('en-GB', {
            timeZone: tz,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
        return dtf.format(date);
    } catch (err) {
        console.warn('[ssbk] formatSlotTime failed', err);
        return null;
    }
}

function refreshSlots() {
    var tzSelect = document.getElementById('ssbk-timezone');
    var slotButtons = document.querySelectorAll('.ssbk-slot');
    if (!tzSelect || !slotButtons.length) { return; }
    var tz = tzSelect.value || ALLOWED_TZ[0];
    var now = Date.now();

    slotButtons.forEach(function (btn) {
        var utcIso = btn.dataset.utc;
        var localEl = btn.querySelector('.ssbk-slot-local');
        var localLabel = formatSlotTime(utcIso, tz);
        if (localEl) {
            localEl.textContent = localLabel || '--:--';
        }
        var slotDate = new Date(utcIso);
        if (!isNaN(slotDate.getTime()) && slotDate.getTime() < now - 60000) {
            btn.classList.add('is-past');
            btn.disabled = true;
        } else {
            btn.classList.remove('is-past');
            btn.disabled = false;
        }
    });
}
```

Keep these existing behaviors:

- timezone detection via `Intl.DateTimeFormat().resolvedOptions().timeZone`
- mapping nearby zones to the whitelist
- slot click sets `#ssbk-slot-input`
- submit validation blocks missing name/email/company/timezone/slot
- invalid fields receive `is-invalid`

- [ ] **Step 7: Validate XML parses locally**

Run:

```bash
python - <<'PY'
from pathlib import Path
from lxml import etree
path = Path('custom_addons/smart_booking/views/booking_templates.xml')
etree.parse(str(path))
print('XML OK')
PY
```

Expected output:

```text
XML OK
```

---

### Task 5: Redesign the thank-you QWeb page and display safe booking summary

**Files:**
- Modify: `custom_addons/smart_booking/views/booking_templates.xml:1163-1580`

- [ ] **Step 1: Remove Google font dependencies from the thank-you page head**

In the `booking_thanks` template, replace the current `head` block with either no custom font links or this minimal title-only setup:

```xml
<t t-set="head"/>
```

- [ ] **Step 2: Replace the dark thank-you page markup with a light success card**

Replace the thank-you template body under `<div class="ssbk-page ssbk-thanks-page">` with:

```xml
<header class="ssbk-site-header">
    <a class="ssbk-logo" href="/" aria-label="Steamships home">Steamships</a>
    <nav class="ssbk-nav" aria-label="Booking navigation">
        <a href="/">Home</a>
        <a href="/contactus">Contact us</a>
        <a class="is-active" href="/steamships/booking">Booking</a>
    </nav>
</header>

<main class="ssbk-thanks-shell">
    <section class="ssbk-thanks-card">
        <div class="ssbk-thanks-icon" aria-hidden="true">✓</div>
        <p class="ssbk-card-tag">Confirmed</p>
        <h1 class="ssbk-thanks-title">Your meeting is booked</h1>
        <p class="ssbk-thanks-sub">
            We’ve saved the meeting to Odoo Calendar. You can add it to your own
            Google Calendar below.
        </p>

        <t t-if="event">
            <div class="ssbk-thanks-detail">
                <div class="ssbk-thanks-row">
                    <span>Meeting type</span>
                    <strong><t t-esc="event.get('meeting_label') or event.get('name')"/></strong>
                </div>
                <div class="ssbk-thanks-row">
                    <span>Your time</span>
                    <strong>
                        <t t-if="event.get('start_client_label')">
                            <t t-esc="event['start_client_label']"/>
                        </t>
                        <t t-else="">
                            <t t-esc="event['start_png_label']"/>
                        </t>
                    </strong>
                </div>
                <div class="ssbk-thanks-row">
                    <span>PNG time</span>
                    <strong><t t-esc="event['start_png_label']"/> – <t t-esc="event['stop_png_label']"/></strong>
                </div>
                <div class="ssbk-thanks-row">
                    <span>Email</span>
                    <strong><t t-esc="event.get('public_summary', {}).get('email') or '—'"/></strong>
                </div>
                <div class="ssbk-thanks-row">
                    <span>Company</span>
                    <strong><t t-esc="event.get('public_summary', {}).get('company') or '—'"/></strong>
                </div>
            </div>

            <div class="ssbk-thanks-actions">
                <a t-att-href="event['google_url']" target="_blank"
                   rel="noopener noreferrer" class="ssbk-btn ssbk-btn-primary">
                    Add to Google Calendar
                </a>
                <a href="/" class="ssbk-btn ssbk-btn-secondary">Back to Website</a>
            </div>
        </t>
        <t t-else="">
            <div class="ssbk-banner ssbk-banner-warn">
                Booking session missing or expired. Please book again if needed.
            </div>
            <div class="ssbk-thanks-actions">
                <a href="/steamships/booking" class="ssbk-btn ssbk-btn-primary">Book a meeting</a>
                <a href="/" class="ssbk-btn ssbk-btn-secondary">Back to Website</a>
            </div>
        </t>
    </section>
</main>
```

- [ ] **Step 3: Replace thank-you CSS with light success-card styles**

Replace the thank-you `<style>` block with either the same shared booking CSS from Task 4 plus these thank-you-specific additions, or keep only additions if the shared CSS is in the same template scope:

```css
.ssbk-thanks-page { min-height: 100vh; background: linear-gradient(180deg, #ffffff 0%, #f6f9fc 100%); }
.ssbk-thanks-shell { max-width: 760px; margin: 0 auto; padding: 54px 24px 78px; }
.ssbk-thanks-card { background: #fff; border: 1px solid #dbe5f0; border-radius: 26px; box-shadow: 0 24px 60px rgba(20, 54, 96, .14); padding: 42px; text-align: center; }
.ssbk-thanks-icon { width: 72px; height: 72px; margin: 0 auto 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: #e8f8ef; color: #16834a; font-size: 2.1rem; font-weight: 900; }
.ssbk-thanks-title { color: #10233f; font-size: clamp(2rem, 4vw, 3rem); line-height: 1.08; letter-spacing: -.03em; margin: 0 0 12px; font-weight: 850; }
.ssbk-thanks-sub { color: #637184; line-height: 1.65; max-width: 34rem; margin: 0 auto 26px; }
.ssbk-thanks-detail { text-align: left; border: 1px solid #dbe5f0; border-radius: 18px; background: #f8fbff; padding: 8px 18px; margin: 24px 0; }
.ssbk-thanks-row { display: flex; justify-content: space-between; gap: 18px; padding: 14px 0; border-bottom: 1px solid #e4edf7; color: #637184; }
.ssbk-thanks-row:last-child { border-bottom: 0; }
.ssbk-thanks-row strong { color: #10233f; text-align: right; }
.ssbk-thanks-actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.ssbk-btn { display: inline-flex; align-items: center; justify-content: center; border-radius: 14px; padding: 13px 20px; font-weight: 800; text-decoration: none; border: 1px solid transparent; }
.ssbk-btn-primary { background: #1266d6; color: #fff; box-shadow: 0 14px 28px rgba(18, 102, 214, .22); }
.ssbk-btn-primary:hover { background: #0d57bc; color: #fff; }
.ssbk-btn-secondary { background: #fff; color: #1266d6; border-color: #cbd8e6; }
.ssbk-btn-secondary:hover { border-color: #1266d6; background: #f0f7ff; color: #0d57bc; }
.ssbk-banner-warn { background: #fff8e6; border-color: #f5d48a; color: #8a5a00; }
@media (max-width: 620px) {
    .ssbk-thanks-card { padding: 28px 20px; border-radius: 20px; }
    .ssbk-thanks-row { flex-direction: column; gap: 4px; }
    .ssbk-thanks-row strong { text-align: left; }
    .ssbk-thanks-actions { flex-direction: column; }
}
```

- [ ] **Step 4: Validate XML parses locally**

Run:

```bash
python - <<'PY'
from pathlib import Path
from lxml import etree
path = Path('custom_addons/smart_booking/views/booking_templates.xml')
etree.parse(str(path))
print('XML OK')
PY
```

Expected output:

```text
XML OK
```

---

### Task 6: Run module update, restart Odoo, and verify manually

**Files:**
- Modify: none
- Validate: `custom_addons/smart_booking/controllers/main.py`
- Validate: `custom_addons/smart_booking/views/booking_templates.xml`

- [ ] **Step 1: Run final syntax checks**

Run:

```bash
python -m py_compile custom_addons/smart_booking/controllers/main.py
python - <<'PY'
from pathlib import Path
from lxml import etree
path = Path('custom_addons/smart_booking/views/booking_templates.xml')
etree.parse(str(path))
print('XML OK')
PY
```

Expected output includes:

```text
XML OK
```

- [ ] **Step 2: Update the Odoo module**

Run:

```bash
./scripts/update-module.sh smart_booking
```

Expected: module update completes successfully. If it fails, read the traceback and fix the exact XML/Python issue before continuing.

- [ ] **Step 3: Restart only the Odoo service**

Because `controllers/main.py` changed, run:

```bash
docker compose restart odoo
```

Expected: the `odoo` service restarts. Do not restart `db`.

- [ ] **Step 4: Manual test guest booking without `lead_id`**

Open:

```text
http://localhost:8069/steamships/booking
```

Verify:

- Page uses a light background, blue primary buttons, rounded white cards, and the custom Steamships mini-header.
- Public user can view the page without login.
- Submit a booking with a unique email and no `lead_id`.
- A `calendar.event` is created with:
  - `x_steamships_booking = True`
  - `x_steamships_lead_id` set
  - `x_steamships_client_timezone` set
  - `x_steamships_meeting_type` set
- A new CRM lead/opportunity is created with name `Website Booking - <Company>`.
- The created event links to the created CRM lead.

- [ ] **Step 5: Manual test booking with `lead_id`**

Open a CRM lead, click **Booking Link**, and submit a booking.

Verify:

- A `calendar.event` is created.
- The event's `x_steamships_lead_id` is the original lead.
- The original lead chatter receives the booking note.
- The event appears in the Smart Booking menu/action.
- If the salesperson has Google Calendar connected, the existing Google sync still works; if not connected, the booking still succeeds and the thank-you page still offers Add to Google Calendar.

- [ ] **Step 6: Manual UI behavior test**

On desktop and mobile widths, verify:

- Available slots are not all strikethrough.
- Selected slot is clearly highlighted blue.
- Timezone changes update slot labels.
- Slot secondary label still shows PNG time.
- Mobile layout is readable with form fields stacked.

---

## Self-review

Spec coverage:

- Light website-style booking page: Task 4.
- Custom public mini-header: Task 4.
- Meeting type selected/unselected states: Task 4.
- Clear selectable slots: Tasks 1 and 4.
- Upcoming business-day slots: Task 1.
- Guest booking without `lead_id` creates CRM lead: Task 2.
- Existing valid `lead_id` linkage preserved: Task 2.
- Public safety boundaries and honeypot: Task 2.
- Thank-you page with meeting/time/email/company and Google Calendar template link: Tasks 3 and 5.
- Calendar/CRM/Google integration preservation: Tasks 2, 3, and 6.
- Acceptance commands and manual tests: Task 6.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or `similar to` placeholders are intentionally left in the plan.

Type and name consistency:

- Controller context uses `slot_days` in Task 1 and template uses `slot_days` in Task 4.
- Public slot payload uses `key`, `utc_iso`, and `label_png`; template data attributes and JS consume those names.
- Honeypot field name is `website_url` in both controller and template.
- Thank-you summary key is `public_summary` in both controller and template.
