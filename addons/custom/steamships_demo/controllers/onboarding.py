"""
Steamships Onboarding Form - HTTP controller (Bước 2)

Public route (auth='public') for client self-service onboarding.
Receives form data → creates res.partner + crm.lead in Steamships pipeline.

Per DOCX B2:
- Fields: company_name, contact_person, email, phone, country, industry,
          service_needed, file upload (multiple)
- Required: key fields
- On submit: auto-create CRM lead (stage="Lead") + attach files
- Bước 3 will add: 24h activity, auto-assign salesperson
"""
import logging

from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ('company_name', 'contact_person', 'email', 'phone',
                   'country', 'industry', 'service_needed')


class SteamshipsOnboarding(http.Controller):

    @http.route('/onboarding', type='http', auth='public', website=True,
                methods=['GET'], csrf=False)
    def onboarding_form(self, **kw):
        """Render the public onboarding form."""
        # Bước 4: dynamic country list (PNG first, then alphabetical)
        countries = self._country_options()
        png_first = sorted(
            [c for c in countries if c[1] == 'Papua New Guinea'],
            key=lambda x: x[1],
        )
        others = sorted(
            [c for c in countries if c[1] != 'Papua New Guinea'],
            key=lambda x: x[1],
        )
        country_list = png_first + others
        return request.render('steamships_demo.onboarding_page', {
            'values': {},
            'error': False,
            'country_list': country_list,
        })

    @http.route('/onboarding/submit', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def onboarding_submit(self, **post):
        """Handle form submission. Create partner + lead.

        Bước 2: just create partner + lead (no activity, no assign yet).
        Bước 3 will add: 24h mail.activity + auto-assign user_id.
        """
        # 1. Validate required fields
        missing = [f for f in REQUIRED_FIELDS if not post.get(f)]
        if missing:
            return request.render('steamships_demo.onboarding_page', {
                'error': _('Missing required fields: %s') % ', '.join(missing),
                'values': post,
            })

        # 2. Create or find partner (by email, dedupe)
        # Use system user to bypass multi-company check on user_id
        SYSTEM = request.env['res.users'].browse(1)
        Partner = request.env['res.partner'].with_user(SYSTEM)
        Company = request.env['res.company'].with_user(SYSTEM)
        steamships_company = Company.search(
            [('name', 'like', 'Steamships')], limit=1) or Company.browse(request.env.company.id)
        existing = Partner.search([('email', '=', post['email'])], limit=1)
        if existing:
            partner = existing
            # update with new info
            partner.write({
                'name': post['company_name'],
                'phone': post['phone'],
                'country_id': int(post['country']) if post.get('country') else False,
                'customer_rank': 1,
                'company_id': steamships_company.id,
            })
        else:
            partner = Partner.create({
                'name': post['company_name'],
                'email': post['email'],
                'phone': post['phone'],
                'country_id': int(post['country']) if post.get('country') else False,
                'is_company': True,
                'customer_rank': 1,
                'company_id': steamships_company.id,
            })

        # 3. Get "Lead" stage (Steamships)
        stage = request.env.ref('steamships_demo.stage_lead', raise_if_not_found=False)
        stage_id = stage.id if stage else False

        # 4. Get team per industry (Phase 2.6 fix: was hardcoded Shipping)
        team = self._auto_assign_team(post['industry'], SYSTEM)
        team_id = team.id if team else False

        # 4b. Auto-assign salesperson theo industry (Bước 3)
        assigned_user = self._auto_assign_salesperson(post['industry'], SYSTEM)
        user_id = assigned_user.id if assigned_user else False

        # 5. Map industry to division (for steamships_division_id field)
        industry_to_division = {
            'logistics': 'steamships_demo.division_logistics',
            'property': 'steamships_demo.division_property',
            'hospitality': 'steamships_demo.division_hotels',
            'joint_venture': False,  # JV không thuộc division cụ thể
        }
        division_ref = industry_to_division.get(post['industry'])
        division = request.env.ref(division_ref,
                                   raise_if_not_found=False) if division_ref else None
        division_id = division.id if division else False

        # 6. Create crm.lead
        Lead = request.env['crm.lead'].with_user(SYSTEM)
        lead = Lead.create({
            'name': _('%s - %s inquiry') % (post['company_name'],
                                            post['service_needed'].title()),
            'partner_id': partner.id,
            'contact_name': post['contact_person'],
            'email_from': post['email'],
            'phone': post['phone'],
            'country_id': int(post['country']) if post.get('country') else False,
            'description': _('Industry: %s\nService needed: %s\n\nNotes:\n%s') % (
                dict(self._industry_options()).get(post['industry'], post['industry']),
                dict(self._service_options()).get(post['service_needed'],
                                                  post['service_needed']),
                post.get('notes', ''),
            ),
            'type': 'opportunity',
            'stage_id': stage_id,
            'team_id': team_id,
            'user_id': user_id,  # Bước 3: auto-assign theo industry
            'steamships_division_id': division_id,
            'company_id': steamships_company.id,
        })

        # 7. Attach uploaded files (multiple)
        # request.httprequest.files gives all uploaded files
        import base64
        files = request.httprequest.files.getlist('attachments')
        if files:
            Attachment = request.env['ir.attachment'].with_user(SYSTEM)
            for f in files:
                if not f or not f.filename:
                    continue
                data = f.read()
                Attachment.create({
                    'name': f.filename,
                    'datas': base64.b64encode(data),
                    'res_model': 'crm.lead',
                    'res_id': lead.id,
                    'type': 'binary',
                    'company_id': steamships_company.id,
                })
            _logger.info('Onboarding form: attached %d files to lead %d',
                         len(files), lead.id)

        # 8. Auto-create KYC onboarding record (draft state)
        Onboarding = request.env['crm.lead.steamships.onboarding'].with_user(SYSTEM)
        Onboarding.create({
            'lead_id': lead.id,
            'industry': post['industry'],
            'service_needed': post['service_needed'],
            'company_size': post.get('company_size', 'mid'),  # default
        })

        # 8b. Auto-move lead to "Onboarding Docs" stage (Phase 1.2)
        # Lead has files attached + KYC started → "Onboarding Docs" is the right stage
        onboarding_stage = request.env.ref(
            'steamships_demo.stage_onboarding_docs', raise_if_not_found=False)
        if onboarding_stage and lead.stage_id != onboarding_stage:
            old_stage_name = lead.stage_id.name if lead.stage_id else 'None'
            lead.write({'stage_id': onboarding_stage.id})
            lead.message_post(
                body=_('CRM stage auto-moved "%s" → "%s" (onboarding form submitted with KYC + files).')
                     % (old_stage_name, onboarding_stage.name),
                subtype_xmlid='mail.mt_note')

        # 9. Chatter log on lead (visible in pipeline)
        lead.message_post(
            body=_('Onboarding form submitted by %s. '
                   'Industry: %s. Service: %s. Files: %d.') % (
                post['contact_person'],
                dict(self._industry_options()).get(post['industry']),
                dict(self._service_options()).get(post['service_needed']),
                len(files),
            ),
            subtype_xmlid='mail.mt_note',
        )

        # 9b. Create 24h follow-up activity (Bước 3)
        # Per DOCX B2: "auto-create an activity reminder: 'Check documents within 24 hours'"
        if user_id:
            from datetime import datetime, timedelta
            Activity = request.env['mail.activity'].with_user(SYSTEM)
            Activity.create({
                'activity_type_id': request.env.ref(
                    'mail.mail_activity_data_todo').id,
                'summary': _('Check documents within 24 hours'),
                'note': _(
                    'New lead from public onboarding form. '
                    'Verify KYC documents and contact the client. '
                    'Reference: %s') % lead.name,
                'res_model_id': request.env['ir.model']._get_id('crm.lead'),
                'res_id': lead.id,
                'user_id': user_id,
                'date_deadline': (datetime.now() + timedelta(hours=24)).date(),
            })
            _logger.info('Onboarding form: 24h activity created for user %s, lead %d',
                         user_id, lead.id)

        # 10. Send confirmation email (Phase 1.3) — best effort, no SMTP needed in dev
        try:
            template = request.env.ref(
                'steamships_demo.mail_template_onboarding_thanks',
                raise_if_not_found=False)
            if template and partner.email:
                template.with_user(SYSTEM).send_mail(
                    lead.id, force_send=False, email_values={
                        'email_to': partner.email,
                        'recipient_ids': [(4, partner.id)],
                    })
                _logger.info('Onboarding confirmation email queued for %s',
                             partner.email)
        except Exception as e:
            _logger.warning('Onboarding email failed: %s', e)

        # 11. Render thank-you page with lead id
        return request.render('steamships_demo.onboarding_thanks', {
            'lead': lead,
            'partner': partner,
            'file_count': len(files),
        })

    # --- Helpers ---

    def _auto_assign_salesperson(self, industry, system_user):
        """Auto-assign salesperson theo industry (DOCX B2 'auto-assign a salesperson').

        Rule (round-robin friendly — for demo, 1 user per industry):
            logistics     -> user_ship_sales
            property      -> user_prop_sales
            hospitality   -> user_hotel_sales
            joint_venture -> user_sales_lead (fallback)

        For production: replace with proper round-robin / workload balance.
        """
        mapping = {
            'logistics': 'steamships_demo.user_ship_sales',
            'property': 'steamships_demo.user_prop_sales',
            'hospitality': 'steamships_demo.user_hotel_sales',
            'joint_venture': 'steamships_demo.user_sales_lead',
        }
        xmlid = mapping.get(industry, 'steamships_demo.user_sales_lead')
        user = request.env.ref(xmlid, raise_if_not_found=False)
        if not user:
            _logger.warning('Auto-assign: user xmlid %s not found', xmlid)
            return False
        _logger.info('Auto-assign: industry=%s -> user=%s (id %s)',
                     industry, user.name, user.id)
        return user

    def _auto_assign_team(self, industry, system_user):
        """Map industry → sales team (Phase 2.6 fix).

        Rule:
            logistics     -> crm_team_logistics
            property      -> crm_team_property
            hospitality   -> crm_team_hotels
            joint_venture -> crm_team_shipping (fallback — JV usually via shipping)
        """
        mapping = {
            'logistics': 'steamships_demo.crm_team_logistics',
            'property': 'steamships_demo.crm_team_property',
            'hospitality': 'steamships_demo.crm_team_hotels',
            'joint_venture': 'steamships_demo.crm_team_shipping',
        }
        xmlid = mapping.get(industry, 'steamships_demo.crm_team_shipping')
        team = request.env.ref(xmlid, raise_if_not_found=False)
        if not team:
            _logger.warning('Auto-team: xmlid %s not found, using fallback', xmlid)
            team = request.env['crm.team'].search(
                [('name', '=', 'Shipping')], limit=1)
        if team:
            _logger.info('Auto-team: industry=%s -> team=%s',
                         industry, team.name)
        return team

    def _industry_options(self):
        """Return industry selection (mirror crm.lead.steamships.onboarding model)."""
        Onboarding = request.env['crm.lead.steamships.onboarding']
        return Onboarding._fields['industry'].selection

    def _service_options(self):
        """Return service_needed selection."""
        Onboarding = request.env['crm.lead.steamships.onboarding']
        return Onboarding._fields['service_needed'].selection

    def _country_options(self):
        """Return list of (id, name) for countries - top 10 + PNG default."""
        Country = request.env['res.country']
        countries = Country.search([], order='name')
        return [(c.id, c.name) for c in countries]
