"""Tests for steamships.division model."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDivision(TransactionCase):

    def test_compute_branch_count(self):
        """Creating a division with branches updates branch_count."""
        Division = self.env['steamships.division']
        Branch = self.env['steamships.branch']

        d = Division.create({
            'name': 'Test Shipping',
            'code': 'TST',
        })
        self.assertEqual(d.branch_count, 0)

        Branch.create({
            'name': 'Test Branch 1',
            'code': 'TB1',
            'division_id': d.id,
        })
        d.invalidate_recordset()
        self.assertEqual(d.branch_count, 1)

    def test_code_unique_constraint(self):
        """Duplicate codes are blocked at DB level."""
        Division = self.env['steamships.division']
        Division.create({'name': 'D1', 'code': 'UNQ'})
        with self.assertRaises(Exception):
            Division.create({'name': 'D2', 'code': 'UNQ'})
