"""Tests for steamships.appointment.slot (Feature 5 Booking)."""
import re
from datetime import datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBookingSlot(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Slot = cls.env['steamships.appointment.slot']
        cls.sales_lead = cls.env.ref('steamships_demo.user_sales_lead')
        # Future weekday at 10:00 PNG time
        now = datetime.now()
        days_ahead = 1
        while True:
            future = now + timedelta(days=days_ahead)
            if future.weekday() < 5 and future.hour < 9:
                break
            days_ahead += 1
        cls.future_start = future.replace(hour=10, minute=0, second=0, microsecond=0)

    def _make_slot(self, **overrides):
        vals = {
            'partner_name': 'Test Visitor',
            'partner_email': 'visitor@example.pg',
            'partner_phone': '+675 123 4567',
            'appointment_type': 'sales_call',
            'duration_minutes': 30,
            'start_datetime': self.future_start,
            'assigned_user_id': self.sales_lead.id,
        }
        vals.update(overrides)
        return self.Slot.create(vals)

    def test_create_slot_minimal(self):
        slot = self._make_slot()
        self.assertEqual(slot.state, 'pending')
        self.assertTrue(slot.name.startswith('SS-AP'))
        self.assertEqual(slot.duration_minutes, 30)

    def test_sequence_unique(self):
        s1 = self._make_slot(partner_name='A')
        s2 = self._make_slot(partner_name='B', start_datetime=(
            self.future_start + timedelta(hours=1)))
        self.assertNotEqual(s1.name, s2.name)

    def test_duration_must_be_30_or_60(self):
        with self.assertRaises(Exception):
            self._make_slot(duration_minutes=45)

    def test_working_hours_enforced(self):
        # 06:00 is outside 09:00-17:00
        early = self.future_start.replace(hour=6)
        with self.assertRaises(Exception):
            self._make_slot(start_datetime=early, partner_name='Early Bird')

    def test_png_9am_slot_passes(self):
        """09:00 PNG wall clock should pass working hours check (regression)."""
        slot = self._make_slot(
            start_datetime=self.future_start.replace(hour=9, minute=0),
            partner_name='9am Visitor',
        )
        self.assertEqual(slot.state, 'pending')

    def test_png_8am_blocked(self):
        """08:00 PNG should fail working hours check (regression)."""
        with self.assertRaises(Exception):
            self._make_slot(
                start_datetime=self.future_start.replace(hour=8),
                partner_name='Early Bird 8am',
            )

    def test_png_17_boundary_blocked(self):
        """17:00 PNG is outside 09:00-17:00 (boundary)."""
        with self.assertRaises(Exception):
            self._make_slot(
                start_datetime=self.future_start.replace(hour=17),
                partner_name='17:00 Visitor',
            )

    def test_png_1659_last_valid(self):
        """16:59 PNG is inside 09:00-17:00 (last valid)."""
        # Note: start_datetime at 16:59 with 30-min duration would end at 17:29
        # which crosses 17:00 boundary. We only check start, not end, per current
        # business rule. Verify start check passes.
        slot = self._make_slot(
            start_datetime=self.future_start.replace(hour=16, minute=59),
            partner_name='Late Visitor',
        )
        self.assertEqual(slot.state, 'pending')

    def test_no_double_booking(self):
        slot = self._make_slot()
        # Try to book another slot at same time with same user
        with self.assertRaises(Exception):
            self._make_slot(partner_name='Second Visitor',
                            start_datetime=slot.start_datetime)

    def test_confirm_creates_calendar_event(self):
        slot = self._make_slot()
        slot.action_confirm()
        self.assertEqual(slot.state, 'confirmed')
        self.assertTrue(slot.calendar_event_id)
        # Calendar event should have the assigned user as attendee
        evt = slot.calendar_event_id
        self.assertIn(self.sales_lead.partner_id, evt.partner_ids)

    def test_confirm_sends_email_with_ics(self):
        slot = self._make_slot()
        slot.action_confirm()
        # Attachment should exist on slot
        ics_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'steamships.appointment.slot'),
            ('res_id', '=', slot.id),
            ('mimetype', '=', 'text/calendar'),
        ])
        self.assertEqual(len(ics_attachments), 1)
        # ICS content should have VCALENDAR/VEVENT
        ics_content = ics_attachments.datas.decode('utf-8') \
            if isinstance(ics_attachments.datas, bytes) \
            else ics_attachments.datas
        self.assertIn('BEGIN:VCALENDAR', ics_content)
        self.assertIn('BEGIN:VEVENT', ics_content)
        self.assertIn('SUMMARY:', ics_content)

    def test_cancel_removes_calendar_event(self):
        slot = self._make_slot()
        slot.action_confirm()
        self.assertTrue(slot.calendar_event_id)
        evt_id = slot.calendar_event_id.id
        slot.action_cancel()
        self.assertEqual(slot.state, 'cancelled')
        self.assertFalse(self.env['calendar.event'].browse(evt_id).exists())

    def test_get_available_slots(self):
        # Create a confirmed slot to block 1 slot
        slot = self._make_slot()
        slot.action_confirm()
        # Get slots for that date
        target_date = slot.start_datetime.date()
        slots = self.Slot.get_available_slots(
            target_date, target_date, duration=30)
        # Available list should NOT include the booked time
        labels = [s['label'] for s in slots]
        booked_label = slot.start_datetime.strftime('%H:%M')
        self.assertNotIn(booked_label, labels)

    def test_ics_format_rfc5545(self):
        slot = self._make_slot()
        ics = slot._generate_ics()
        # Verify RFC 5545 structure
        self.assertIn('BEGIN:VCALENDAR', ics)
        self.assertIn('END:VCALENDAR', ics)
        self.assertIn('VERSION:2.0', ics)
        self.assertIn('PRODID:', ics)
        self.assertIn('UID:', ics)
        # UTC datetime format: YYYYMMDDTHHMMSSZ
        dtstart_match = re.search(r'DTSTART:(\d{8}T\d{6}Z)', ics)
        self.assertIsNotNone(dtstart_match)
        # PNG GMT+10 → UTC is 10 hours behind (in ics, DTSTART should be 00:00Z for 10:00 PNG)
        # Slot start = 10:00 local → 00:00 UTC same day
        self.assertIn('T000000Z', ics)


@tagged('post_install', '-at_install')
class TestIcsGenerator(TransactionCase):
    """Direct test of tools/ics_generator.py."""

    def test_generate_ics_minimal(self):
        from odoo.addons.steamships_demo.tools.ics_generator import generate_ics
        from datetime import datetime
        ics = generate_ics({
            'uid': 'test-123@steamships.com.pg',
            'start': datetime(2026, 6, 20, 10, 0),  # 10:00 PNG = 00:00 UTC
            'end': datetime(2026, 6, 20, 11, 0),    # 11:00 PNG = 01:00 UTC
            'summary': 'Sales Call',
        })
        self.assertIn('BEGIN:VCALENDAR', ics)
        self.assertIn('UID:test-123@steamships.com.pg', ics)
        self.assertIn('SUMMARY:Sales Call', ics)
        self.assertIn('DTSTART:20260620T000000Z', ics)
        self.assertIn('DTEND:20260620T010000Z', ics)
        self.assertIn('END:VCALENDAR', ics)

    def test_escape_special_chars(self):
        from odoo.addons.steamships_demo.tools.ics_generator import (
            generate_ics, _escape)
        # Comma, semicolon, backslash, newline all escaped
        self.assertEqual(_escape('a,b'), r'a\,b')
        self.assertEqual(_escape('a;b'), r'a\;b')
        self.assertEqual(_escape('a\\b'), r'a\\b')
        self.assertEqual(_escape('a\nb'), r'a\nb')
