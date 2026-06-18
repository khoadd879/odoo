"""ICS file generator — minimal RFC 5545 implementation.

No PyPI dep (icalendar / vobject not installed in this project).
Used by models/appointment_slot.py to build calendar invitations.
"""
from datetime import datetime, timezone, timedelta


def generate_ics(event_data):
    """Build a complete VCALENDAR string from event_data dict.

    Required keys:
        uid: str (e.g. 'evt-123@steamships.com.pg')
        start: datetime (naive = PNG GMT+10, tz-aware = respected)
        end: datetime
        summary: str
    Optional keys:
        description, location, organizer_email, attendee_email, attendee_name
    """
    uid = event_data['uid']
    start = _to_utc(event_data['start'])
    end = _to_utc(event_data['end'])
    summary = _escape(event_data.get('summary', ''))
    description = _escape(event_data.get('description', ''))
    location = _escape(event_data.get('location', 'Steamships HQ, Port Moresby, PNG'))
    organizer = _escape(event_data.get('organizer_email', 'sales@steamships.com.pg'))
    attendee = _escape(event_data.get('attendee_email', ''))
    attendee_name = _escape(event_data.get('attendee_name', ''))
    now_utc = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return (
        'BEGIN:VCALENDAR\r\n'
        'VERSION:2.0\r\n'
        'PRODID:-//Steamships//Booking//EN\r\n'
        'CALSCALE:GREGORIAN\r\n'
        'METHOD:REQUEST\r\n'
        'BEGIN:VEVENT\r\n'
        f'UID:{uid}\r\n'
        f'DTSTAMP:{now_utc}\r\n'
        f'DTSTART:{start}\r\n'
        f'DTEND:{end}\r\n'
        f'SUMMARY:{summary}\r\n'
        f'DESCRIPTION:{description}\r\n'
        f'LOCATION:{location}\r\n'
        f'ORGANIZER;CN=Steamships:mailto:{organizer}\r\n'
        f'ATTENDEE;CN={attendee_name};RSVP=TRUE:mailto:{attendee}\r\n'
        'STATUS:CONFIRMED\r\n'
        'END:VEVENT\r\n'
        'END:VCALENDAR\r\n'
    )


def _to_utc(dt):
    """Treat naive datetime as PNG wall clock (GMT+10), return UTC string."""
    if dt is None:
        return ''
    if dt.tzinfo is None:
        png_tz = timezone(timedelta(hours=10))
        dt = dt.replace(tzinfo=png_tz)
    return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _escape(text):
    """RFC 5545 text escape."""
    if not text:
        return ''
    return (str(text)
            .replace('\\', '\\\\')
            .replace(',', '\\,')
            .replace(';', '\\;')
            .replace('\n', '\\n'))
