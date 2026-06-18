"""Tests for the public onboarding flow + KYC auto-progression.

Covers:
- Onboarding record creation + completion %
- State machine: draft → in_progress → kyc_done → approved
- Reset to draft + Reopen from rejected
- Reject path
- CRM stage auto-progression (Lead → Onboarding Docs → Quoted)
- Chatter messages
- File attachments via ir.attachment
- crm.lead related fields (onboarding_id/state/completion)
"""
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('post_install', '-at_install')
class TestOnboardingKycFlow(TransactionCase):
    """Core onboarding record lifecycle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Onboarding = cls.env['crm.lead.steamships.onboarding']
        cls.Lead = cls.env['crm.lead']
        cls.Attachment = cls.env['ir.attachment']
        cls.sales_lead = cls.env.ref('steamships_demo.user_sales_lead')
        cls.stage_lead = cls.env.ref('steamships_demo.stage_lead')
        cls.stage_onboarding = cls.env.ref('steamships_demo.stage_onboarding_docs')
        cls.stage_quoted = cls.env.ref('steamships_demo.stage_quoted')
        cls.stage_won = cls.env.ref('steamships_demo.stage_won')

    def _make_lead(self, **overrides):
        """Create a CRM lead in the 'Lead' stage (default for new opps)."""
        vals = {
            'name': 'Test Lead',
            'type': 'opportunity',
            'user_id': self.sales_lead.id,
            'stage_id': self.stage_lead.id,
        }
        vals.update(overrides)
        return self.Lead.create(vals)

    def _make_onboarding(self, lead, **onb_overrides):
        """Create onboarding record in draft state for given lead."""
        vals = {
            'lead_id': lead.id,
            'industry': 'logistics',
            'service_needed': 'shipping',
            'company_size': 'mid',
        }
        vals.update(onb_overrides)
        return self.Onboarding.create(vals)

    def _mark_all_kyc(self, ob):
        """Tick all 8 KYC booleans → completion_pct = 100."""
        ob.write({
            'ipa_cert': True, 'ipa_cert_date': '2026-01-01',
            'tax_id': True, 'tax_id_ref': 'TIN-12345',
            'bank_ref': True, 'bank_ref_date': '2026-01-15',
            'directors_id': True, 'pep_check': True,
            'credit_check': True, 'insurance_cert': True,
            'contract_signed': True,
        })

    # ─── Creation + defaults ────────────────────────────────────────

    def test_01_create_onboarding_sets_lead(self):
        """Fresh onboarding links to lead, state=draft, completion=0."""
        lead = self._make_lead(name='ACME Shipping')
        ob = self._make_onboarding(lead, industry='logistics',
                                   service_needed='shipping',
                                   company_size='mid')
        self.assertEqual(ob.lead_id, lead)
        self.assertEqual(ob.onboarding_state, 'draft')
        self.assertEqual(ob.completion_pct, 0)

    def test_02_industry_selection_all_four(self):
        """All 4 industries from DOCX B2 are accepted."""
        industries = ['logistics', 'property', 'hospitality', 'joint_venture']
        for ind in industries:
            lead = self._make_lead(name=f'Test {ind}')
            ob = self._make_onboarding(lead, industry=ind)
            self.assertEqual(ob.industry, ind)

    def test_03_completion_pct_zero(self):
        """No KYC ticked → 0%."""
        ob = self._make_onboarding(self._make_lead())
        self.assertEqual(ob.completion_pct, 0)

    def test_04_completion_pct_partial(self):
        """4/8 ticked → 50%."""
        ob = self._make_onboarding(self._make_lead())
        ob.write({
            'ipa_cert': True, 'tax_id': True,
            'bank_ref': True, 'directors_id': True,
        })
        self.assertEqual(ob.completion_pct, 50)

    def test_05_completion_pct_full(self):
        """All 8 ticked → 100%."""
        ob = self._make_onboarding(self._make_lead())
        self._mark_all_kyc(ob)
        self.assertEqual(ob.completion_pct, 100)

    def test_06_completion_pct_25(self):
        """2/8 ticked → 25% (integer division)."""
        ob = self._make_onboarding(self._make_lead())
        ob.write({'ipa_cert': True, 'tax_id': True})
        self.assertEqual(ob.completion_pct, 25)

    def test_07_completion_pct_decrements(self):
        """Untick a field → completion decreases."""
        ob = self._make_onboarding(self._make_lead())
        ob.write({'ipa_cert': True, 'tax_id': True})
        self.assertEqual(ob.completion_pct, 25)
        ob.write({'ipa_cert': False})
        self.assertEqual(ob.completion_pct, 12)  # 1/8 = 12.5 → int 12

    # ─── State machine ──────────────────────────────────────────────

    def test_10_start_kyc_from_draft(self):
        """Start button: draft → in_progress."""
        ob = self._make_onboarding(self._make_lead())
        ob.action_start()
        self.assertEqual(ob.onboarding_state, 'in_progress')

    def test_11_cannot_mark_kyc_done_below_100(self):
        """Mark KYC Complete requires 100% — should NOT change state."""
        ob = self._make_onboarding(self._make_lead())
        ob.write({'ipa_cert': True, 'tax_id': True})  # 25%
        ob.action_start()
        ob.action_mark_kyc_done()
        self.assertEqual(ob.onboarding_state, 'in_progress')

    def test_12_mark_kyc_done_at_100(self):
        """100% completion → can mark KYC done."""
        ob = self._make_onboarding(self._make_lead())
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        self.assertEqual(ob.onboarding_state, 'kyc_done')

    def test_13_approve_after_kyc_done(self):
        """Approve only valid from kyc_done state."""
        ob = self._make_onboarding(self._make_lead())
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        ob.action_approve()
        self.assertEqual(ob.onboarding_state, 'approved')

    def test_14_reject_from_any_state(self):
        """Reject from in_progress, kyc_done all work."""
        for state_setup in ['in_progress', 'kyc_done']:
            ob = self._make_onboarding(self._make_lead(name=f'Reject {state_setup}'))
            self._mark_all_kyc(ob)
            ob.action_start()
            if state_setup == 'kyc_done':
                ob.action_mark_kyc_done()
            ob.action_reject()
            self.assertEqual(ob.onboarding_state, 'rejected')

    # ─── Auto CRM stage progression ─────────────────────────────────

    def test_20_approve_moves_lead_to_quoted(self):
        """Approve → lead auto-moves from Onboarding Docs → Quoted."""
        lead = self._make_lead(stage_id=self.stage_onboarding.id)
        ob = self._make_onboarding(lead)
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        ob.action_approve()
        self.assertEqual(lead.stage_id, self.stage_quoted)

    def test_21_approve_idempotent_when_already_quoted(self):
        """If lead already Quoted, re-approve doesn't move again (no double chatter)."""
        lead = self._make_lead(stage_id=self.stage_quoted.id)
        ob = self._make_onboarding(lead)
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        msgs_before = len(lead.message_ids)
        ob.action_approve()
        self.assertEqual(lead.stage_id, self.stage_quoted)
        # No new chatter message about stage auto-move
        stage_msgs = lead.message_ids.filtered(
            lambda m: 'CRM stage auto-moved' in (m.body or ''))
        self.assertEqual(len(stage_msgs), 0)

    def test_22_reset_from_approved_moves_back(self):
        """Reset from approved → lead moves Quoted → Onboarding Docs."""
        lead = self._make_lead(stage_id=self.stage_quoted.id)
        ob = self._make_onboarding(lead)
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        ob.action_approve()
        self.assertEqual(lead.stage_id, self.stage_quoted)
        ob.action_reset_to_draft()
        self.assertEqual(ob.onboarding_state, 'draft')
        self.assertEqual(lead.stage_id, self.stage_onboarding)

    def test_23_reset_from_in_progress_no_stage_change(self):
        """Reset from in_progress → draft, but lead stays Onboarding Docs."""
        lead = self._make_lead(stage_id=self.stage_onboarding.id)
        ob = self._make_onboarding(lead)
        ob.write({'ipa_cert': True, 'tax_id': True})
        ob.action_start()
        ob.action_reset_to_draft()
        self.assertEqual(ob.onboarding_state, 'draft')
        self.assertEqual(lead.stage_id, self.stage_onboarding)

    def test_24_reopen_from_rejected(self):
        """Rejected → Reopen → draft."""
        ob = self._make_onboarding(self._make_lead())
        ob.action_reject()
        self.assertEqual(ob.onboarding_state, 'rejected')
        ob.action_reopen_from_rejected()
        self.assertEqual(ob.onboarding_state, 'draft')

    def test_25_reopen_ignored_when_not_rejected(self):
        """Reopen on non-rejected state is a no-op (silent)."""
        ob = self._make_onboarding(self._make_lead())
        ob.action_start()  # in_progress
        ob.action_reopen_from_rejected()  # should NOT change state
        self.assertEqual(ob.onboarding_state, 'in_progress')

    def test_26_reset_from_kyc_done_keeps_lead_in_onboarding(self):
        """Reset from kyc_done → draft, lead stays in Onboarding Docs
        (was never auto-moved because kyc_done ≠ approved)."""
        lead = self._make_lead(stage_id=self.stage_onboarding.id)
        ob = self._make_onboarding(lead)
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        ob.action_reset_to_draft()
        self.assertEqual(ob.onboarding_state, 'draft')
        # Lead wasn't moved to Quoted yet
        self.assertEqual(lead.stage_id, self.stage_onboarding)

    # ─── Chatter assertions ─────────────────────────────────────────

    def test_30_chatter_posted_on_approve(self):
        """Approve posts message: 'Onboarding APPROVED. KYC 100%...'."""
        lead = self._make_lead()
        ob = self._make_onboarding(lead)
        self._mark_all_kyc(ob)
        ob.action_start()
        ob.action_mark_kyc_done()
        msgs_before = len(lead.message_ids)
        ob.action_approve()
        new_msgs = lead.message_ids[msgs_before:]
        bodies = ' '.join(m.body or '' for m in new_msgs)
        self.assertIn('Onboarding APPROVED', bodies)
        self.assertIn('KYC 100%', bodies)
        self.assertIn('Quoted', bodies)  # auto-stage message

    def test_31_chatter_posted_on_reset(self):
        """Reset to Draft posts message with old state."""
        lead = self._make_lead()
        ob = self._make_onboarding(lead)
        ob.action_start()  # in_progress
        ob.action_reset_to_draft()
        bodies = ' '.join(m.body or '' for m in lead.message_ids)
        self.assertIn('Onboarding reset to Draft', bodies)
        self.assertIn('in_progress', bodies)

    # ─── crm.lead related fields ────────────────────────────────────

    def test_40_onboarding_id_on_lead(self):
        """onboarding_id computed field on crm.lead returns latest onboarding."""
        lead = self._make_lead()
        self.assertFalse(lead.onboarding_id)
        ob1 = self._make_onboarding(lead)
        # refresh lead (compute is store=True but we may need to flush)
        lead.invalidate_recordset()
        self.assertEqual(lead.onboarding_id, ob1)

    def test_41_onboarding_state_related_field(self):
        """onboarding_state on lead mirrors onboarding.onboarding_state."""
        lead = self._make_lead()
        ob = self._make_onboarding(lead)
        lead.invalidate_recordset()
        self.assertEqual(lead.onboarding_state, 'draft')
        ob.action_start()
        lead.invalidate_recordset()
        self.assertEqual(lead.onboarding_state, 'in_progress')

    def test_42_onboarding_completion_related_field(self):
        """onboarding_completion mirrors completion_pct."""
        lead = self._make_lead()
        ob = self._make_onboarding(lead)
        ob.write({'ipa_cert': True, 'tax_id': True, 'bank_ref': True,
                  'directors_id': True})  # 50%
        lead.invalidate_recordset()
        self.assertEqual(lead.onboarding_completion, 50)

    # ─── Onboarding link: crm.lead gets onboarding_id after create ──

    def test_50_lead_links_to_onboarding_after_create(self):
        """After onboarding.create(), lead.onboarding_id is set via search."""
        lead = self._make_lead(name='Link Test')
        ob = self._make_onboarding(lead)
        # Force re-compute (since search-based compute needs invalidation)
        lead._compute_onboarding()
        self.assertEqual(lead.onboarding_id, ob)


@tagged('post_install', '-at_install')
class TestOnboardingAttachments(TransactionCase):
    """ir.attachment link to onboarding/lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Onboarding = cls.env['crm.lead.steamships.onboarding']
        cls.Lead = cls.env['crm.lead']
        cls.Attachment = cls.env['ir.attachment']
        cls.sales_lead = cls.env.ref('steamships_demo.user_sales_lead')

    def _make_lead_with_onboarding(self):
        lead = self.Lead.create({
            'name': 'Attachment Test',
            'type': 'opportunity',
            'user_id': self.sales_lead.id,
        })
        ob = self.Onboarding.create({
            'lead_id': lead.id,
            'industry': 'logistics',
            'service_needed': 'shipping',
            'company_size': 'mid',
        })
        return lead, ob

    def test_60_attach_file_to_lead(self):
        """Attachment with res_model=crm.lead + res_id=lead.id is queryable."""
        import base64
        lead, _ob = self._make_lead_with_onboarding()
        fake_pdf = base64.b64encode(b'%PDF-1.4 fake content')
        att = self.Attachment.create({
            'name': 'ipa_cert.pdf',
            'datas': fake_pdf,
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'type': 'binary',
        })
        self.assertEqual(att.res_model, 'crm.lead')
        self.assertEqual(att.res_id, lead.id)
        # Queryable
        atts = self.Attachment.search([
            ('res_model', '=', 'crm.lead'),
            ('res_id', '=', lead.id),
        ])
        self.assertIn(att, atts)

    def test_61_multiple_attachments_linked(self):
        """Multiple files can attach to same lead."""
        import base64
        lead, _ob = self._make_lead_with_onboarding()
        for i, fname in enumerate(['ipa.pdf', 'tin.pdf', 'bank_ref.pdf']):
            self.Attachment.create({
                'name': fname,
                'datas': base64.b64encode(f'content {i}'.encode()),
                'res_model': 'crm.lead',
                'res_id': lead.id,
                'type': 'binary',
            })
        atts = self.Attachment.search([
            ('res_model', '=', 'crm.lead'),
            ('res_id', '=', lead.id),
        ])
        self.assertEqual(len(atts), 3)


@tagged('post_install', '-at_install')
class TestOnboardingWizard(TransactionCase):
    """Tests for the start-onboarding wizard on crm.lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env['crm.lead']
        cls.sales_lead = cls.env.ref('steamships_demo.user_sales_lead')

    def test_70_action_start_onboarding_returns_wizard(self):
        """action_start_onboarding returns action dict for wizard."""
        lead = self.Lead.create({
            'name': 'Wizard Test',
            'type': 'opportunity',
            'user_id': self.sales_lead.id,
        })
        action = lead.action_start_onboarding()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'],
                         'crm.lead.steamships.onboarding.wizard')
        self.assertEqual(action['context']['default_lead_id'], lead.id)

    def test_71_action_open_onboarding_without_record_returns_wizard(self):
        """action_open_onboarding on lead without onboarding → wizard."""
        lead = self.Lead.create({
            'name': 'No Onboarding',
            'type': 'opportunity',
            'user_id': self.sales_lead.id,
        })
        action = lead.action_open_onboarding()
        # No onboarding yet → falls back to start wizard
        self.assertEqual(action['res_model'],
                         'crm.lead.steamships.onboarding.wizard')

    def test_72_action_open_onboarding_with_record_returns_form(self):
        """action_open_onboarding with existing onboarding → form view."""
        lead = self.Lead.create({
            'name': 'With Onboarding',
            'type': 'opportunity',
            'user_id': self.sales_lead.id,
        })
        ob = self.env['crm.lead.steamships.onboarding'].create({
            'lead_id': lead.id,
            'industry': 'logistics',
            'service_needed': 'shipping',
            'company_size': 'mid',
        })
        action = lead.action_open_onboarding()
        self.assertEqual(action['res_model'],
                         'crm.lead.steamships.onboarding')
        self.assertEqual(action['res_id'], ob.id)
