"""Tests for bill.of.lading model."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBillOfLading(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.BL = cls.env['bill.of.lading']

    def test_create_minimal_bl(self):
        """A BL with only required fields should be savable."""
        bl = self.BL.create({
            'name': 'TEST-001',
            'shipper': 'Acme Shipper',
            'consignee': 'Beta Consignee',
        })
        self.assertEqual(bl.state, 'pending_review')
        self.assertTrue(bl.id)

    def test_approve_transitions_state(self):
        bl = self.BL.create({'name': 'TEST-002'})
        bl.action_approve()
        self.assertEqual(bl.state, 'approved')

    def test_reject_requires_reason(self):
        """Rejection must have review_notes (matches business rule)."""
        bl = self.BL.create({'name': 'TEST-003'})
        with self.assertRaises(Exception):
            bl.action_reject()
        # With notes, reject succeeds
        bl.review_notes = 'Test reject reason — unreadable scan'
        bl.action_reject()
        self.assertEqual(bl.state, 'rejected')

    def test_search_by_state(self):
        self.BL.create({'name': 'TEST-004'})
        results = self.BL.search([('state', '=', 'pending_review')])
        self.assertGreaterEqual(len(results), 1)

    def test_low_confidence_field_decoration(self):
        """Low-confidence fields stored as comma-separated string."""
        bl = self.BL.create({
            'name': 'TEST-005',
            'low_confidence_fields': 'shipper,vessel_name',
        })
        self.assertIn('shipper', bl.low_confidence_fields)
