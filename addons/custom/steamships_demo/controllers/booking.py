"""Steamships Smart Booking — public form (no Enterprise needed).

Routes:
  GET  /booking           — public form, pick date+slot+type
  POST /booking/submit    — create pending slot, redirect to thank-you
  GET  /booking/thanks/<id> — confirmation page (public)
  GET  /booking/calendar/<token> — ICS download (public via signed token)
"""
import logging
from datetime import datetime, timedelta

from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SteamshipsBooking(http.Controller):

    @http.route('/booking', type='http', auth='public', website=True,
                methods=['GET'], csrf=False)
    def booking_form(self, **kw):
        """Render public booking form. Lists available slots for next 14 days."""
        Slot = request.env['steamships.appointment.slot']
        # Salespeople user records available for assignment
        users = request.env['res.users'].sudo().search([
            ('company_ids', 'in', request.env.company.id),
            ('groups_id', 'in', request.env.ref(
                'sales_team.group_sale_salesman_all_leads').id),
        ])
        # Generate date options (next 14 days, skip weekends for demo)
        today = datetime.now().date()
        date_options = []
        for i in range(1, 15):
            d = today + timedelta(days=i)
            if d.weekday() < 5:  # Mon-Fri only
                date_options.append({
                    'value': d.isoformat(),
                    'label': d.strftime('%A, %d %b %Y'),
                })
        # Get all 30-min slots for first day as preview
        sample_slots = Slot.get_available_slots(
            today + timedelta(days=1),
            today + timedelta(days=1),
            duration=30,
        ) if date_options else []
        return request.render('steamships_demo.booking_form_page', {
            'date_options': date_options,
            'sample_slots': sample_slots,
            'users': users,
        })

    @http.route('/booking/submit', type='http', auth='public',
                website=True, methods=['POST'], csrf=False)
    def booking_submit(self, **post):
        """Create pending slot, redirect to thank-you page."""
        required = ('partner_name', 'partner_email', 'appointment_type',
                    'start_datetime', 'duration_minutes')
        missing = [f for f in required if not post.get(f)]
        if missing:
            return request.render('steamships_demo.booking_form_page', {
                'error': _('Missing required fields: %s') % ', '.join(missing),
                'date_options': [],
                'users': request.env['res.users'].sudo().search([]),
            })
        SYSTEM = request.env['res.users'].browse(1)
        Slot = request.env['steamships.appointment.slot'].with_user(SYSTEM)
        # Parse start_datetime from ISO format
        try:
            start_dt = datetime.fromisoformat(post['start_datetime'])
        except (ValueError, TypeError) as e:
            return request.render('steamships_demo.booking_form_page', {
                'error': _('Invalid datetime: %s') % post['start_datetime'],
                'date_options': [],
                'users': request.env['res.users'].sudo().search([]),
            })
        # Find user (salesperson)
        assigned_user = request.env['res.users'].sudo().browse(
            int(post.get('assigned_user_id', 0)) or
            request.env.ref('steamships_demo.user_sales_lead',
                            raise_if_not_found=False).id
        )
        try:
            slot = Slot.create({
                'partner_name': post['partner_name'],
                'partner_email': post['partner_email'],
                'partner_phone': post.get('partner_phone', ''),
                'appointment_type': post['appointment_type'],
                'duration_minutes': int(post['duration_minutes']),
                'start_datetime': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'assigned_user_id': assigned_user.id,
                'notes': post.get('notes', ''),
                'state': 'pending',
            })
        except ValidationError as e:
            return request.render('steamships_demo.booking_form_page', {
                'error': str(e),
                'date_options': [],
                'users': request.env['res.users'].sudo().search([]),
            })
        # Auto-confirm if visitor clicks "Confirm now" (form has 2 buttons)
        if post.get('auto_confirm') == '1':
            slot.with_user(SYSTEM).action_confirm()
        _logger.info('Booking created: %s for %s at %s',
                     slot.name, slot.partner_name, slot.start_datetime)
        return request.render('steamships_demo.booking_thanks', {
            'slot': slot,
        })

    @http.route('/booking/thanks/<int:slot_id>', type='http',
                auth='public', website=True, methods=['GET'], csrf=False)
    def booking_thanks(self, slot_id, **kw):
        Slot = request.env['steamships.appointment.slot'].sudo()
        slot = Slot.browse(slot_id)
        if not slot.exists():
            return request.not_found()
        return request.render('steamships_demo.booking_thanks', {
            'slot': slot,
        })

    @http.route('/booking/calendar/<string:token>', type='http',
                auth='public', methods=['GET'], csrf=False)
    def booking_calendar(self, token, **kw):
        """Public ICS download via signed token (no login required)."""
        Slot = request.env['steamships.appointment.slot'].sudo()
        slot = Slot.search([('confirmation_token', '=', token)], limit=1)
        if not slot:
            return request.not_found()
        ics = slot._generate_ics()
        return request.make_response(
            ics,
            headers=[
                ('Content-Type', 'text/calendar; charset=utf-8'),
                ('Content-Disposition',
                 'attachment; filename="booking_%s.ics"' % slot.name),
            ])

    @http.route('/booking/api/available', type='json', auth='public',
                csrf=False)
    def available_slots(self, date_from, date_to, duration=30, **kw):
        """JSON: list of available slots for the given date range."""
        Slot = request.env['steamships.appointment.slot'].sudo()
        slots = Slot.get_available_slots(date_from, date_to, duration)
        return [{
            'start': s['start'].isoformat(),
            'label': s['label'],
        } for s in slots]
