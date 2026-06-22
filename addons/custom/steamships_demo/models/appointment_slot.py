"""Steamships Appointment Slot — custom booking (no Enterprise needed).

Public visitors book a 30/60-min slot with Steamships sales team.
Slots are PNG time-zone aware (GMT+10, no DST).
On confirm: generate ICS file, create calendar.event, send confirmation email.
"""
import logging
from datetime import datetime, timedelta, timezone

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from odoo.tools import html_escape

from ..tools.ics_generator import generate_ics

_logger = logging.getLogger(__name__)

PNG_TZ_OFFSET = 10  # PNG = GMT+10, no DST
WORK_START_HOUR = 9   # 09:00
WORK_END_HOUR = 17    # 17:00 (last slot ends by 17:00)
SLOT_DURATIONS = (30, 60)


class SteamshipsAppointmentSlot(models.Model):
    _name = 'steamships.appointment.slot'
    _description = 'Steamships Appointment Slot'
    _inherit = ['mail.thread']
    _order = 'start_datetime desc'
    _rec_name = 'name'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default='New')

    # Visitor info
    partner_name = fields.Char(string='Full name', required=True, tracking=True)
    partner_email = fields.Char(string='Email', required=True, tracking=True)
    partner_phone = fields.Char(string='Phone')
    partner_id = fields.Many2one('res.partner', string='Existing partner',
                                 help='Set if visitor matches existing res.partner')

    # Appointment details
    appointment_type = fields.Selection([
        ('sales_call', 'Sales Call (30 min)'),
        ('onboarding', 'Client Onboarding (60 min)'),
        ('demo', 'Product Demo (60 min)'),
    ], string='Type', required=True, default='sales_call')

    duration_minutes = fields.Integer(string='Duration (min)', required=True,
                                       default=30)
    start_datetime = fields.Datetime(string='Start (PNG time GMT+10)',
                                     required=True, tracking=True)
    end_datetime = fields.Datetime(string='End (PNG time GMT+10)',
                                    compute='_compute_end_datetime', store=True)
    assigned_user_id = fields.Many2one('res.users', string='Host (salesperson)',
                                       required=True,
                                       default=lambda s: s._default_assigned_user())
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda s: s.env.company)

    state = fields.Selection([
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('done', 'Done'),
        ('no_show', 'No show'),
    ], default='pending', required=True, tracking=True)

    notes = fields.Text(string='Customer notes')
    internal_notes = fields.Text(string='Internal notes')

    # Link to lead/CRM
    lead_id = fields.Many2one('crm.lead', string='Related CRM Lead')
    calendar_event_id = fields.Many2one('calendar.event', string='Calendar event')

    # Confirmation
    confirmation_token = fields.Char(copy=False, index=True)
    confirmed_at = fields.Datetime()
    cancelled_at = fields.Datetime()
    cancellation_reason = fields.Text()

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Slot reference must be unique.'),
    ]

    @api.model
    def _default_assigned_user(self):
        return self.env.ref('steamships_demo.user_sales_lead',
                            raise_if_not_found=False)

    @api.depends('start_datetime', 'duration_minutes')
    def _compute_end_datetime(self):
        for rec in self:
            if rec.start_datetime and rec.duration_minutes:
                rec.end_datetime = (rec.start_datetime
                                    + timedelta(minutes=rec.duration_minutes))
            else:
                rec.end_datetime = False

    @api.constrains('duration_minutes')
    def _check_duration(self):
        for rec in self:
            if rec.duration_minutes not in SLOT_DURATIONS:
                raise ValidationError(
                    _('Duration must be 30 or 60 minutes.'))

    @api.constrains('start_datetime')
    def _check_working_hours(self):
        for rec in self:
            if not rec.start_datetime:
                continue
            # Convention: start_datetime is naive PNG wall clock (GMT+10, no DST).
            # Odoo Datetime field stores naive values in DB; we intentionally treat
            # the stored value as PNG time for this check. UTC-stored values
            # (e.g. 23:00) would fail this check, which is the desired behavior
            # for the booking flow — submit handler always normalizes to PNG.
            local_hour = rec.start_datetime.hour
            if local_hour < WORK_START_HOUR or local_hour >= WORK_END_HOUR:
                raise ValidationError(_(
                    'Slot must start between 09:00 and 17:00 (PNG time). '
                    'Got: %02d:00' % local_hour))

    @api.constrains('start_datetime', 'assigned_user_id', 'state')
    def _check_no_double_booking(self):
        for rec in self:
            if rec.state not in ('pending', 'confirmed'):
                continue
            # Check overlapping slots for same user
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('assigned_user_id', '=', rec.assigned_user_id.id),
                ('state', 'in', ('pending', 'confirmed')),
                ('start_datetime', '<',
                 rec.end_datetime or (rec.start_datetime + timedelta(hours=1))),
                ('end_datetime', '>', rec.start_datetime),
            ])
            if overlapping:
                raise ValidationError(
                    _('User %s already has a slot at this time: %s')
                    % (rec.assigned_user_id.name, overlapping[0].name))

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'steamships.appointment.slot') or 'New'
        if not vals.get('confirmation_token'):
            import secrets
            vals['confirmation_token'] = secrets.token_urlsafe(16)
        return super().create(vals)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_confirm(self):
        """Confirm slot, create calendar.event, send email with ICS."""
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_('Only pending slots can be confirmed.'))
        # Create linked calendar.event (Community builtin)
        CalendarEvent = self.env['calendar.event'].sudo()
        # Get or create visitor as res.partner (link if not already)
        if not self.partner_id and self.partner_email:
            Visitor = self.env['res.partner'].sudo()
            existing = Visitor.search([('email', '=', self.partner_email)], limit=1)
            if existing:
                self.partner_id = existing
            else:
                self.partner_id = Visitor.create({
                    'name': self.partner_name,
                    'email': self.partner_email,
                    'phone': self.partner_phone,
                })
        if not self.calendar_event_id:
            evt = CalendarEvent.create({
                'name': _('%s — %s') % (
                    dict(self._fields['appointment_type'].selection).get(
                        self.appointment_type, 'Meeting'),
                    self.partner_name),
                'start': self.start_datetime,
                'stop': self.end_datetime,
                'description': self.notes or '',
                'partner_ids': [(6, 0, [
                    self.partner_id.id,
                    self.assigned_user_id.partner_id.id,
                ])] if self.partner_id and self.assigned_user_id.partner_id else False,
                'user_id': self.assigned_user_id.id,
                'company_id': self.company_id.id,
            })
            self.calendar_event_id = evt.id
        self.write({
            'state': 'confirmed',
            'confirmed_at': fields.Datetime.now(),
        })
        # Send email with ICS attachment
        self._send_confirmation_email()
        self.message_post(
            body=_('Booking confirmed. Confirmation email sent to %s.')
                 % self.partner_email,
            subtype_xmlid='mail.mt_note')
        return True

    def action_cancel(self):
        self.ensure_one()
        if self.state in ('done', 'cancelled'):
            raise UserError(_('Slot already finalized.'))
        if self.calendar_event_id:
            self.calendar_event_id.sudo().unlink()
        self.write({
            'state': 'cancelled',
            'cancelled_at': fields.Datetime.now(),
        })
        return True

    def action_mark_done(self):
        self.ensure_one()
        self.write({'state': 'done'})

    def action_mark_no_show(self):
        self.ensure_one()
        self.write({'state': 'no_show'})

    # ------------------------------------------------------------------
    # Email + ICS
    # ------------------------------------------------------------------

    def _send_confirmation_email(self):
        self.ensure_one()
        ics_content = self._generate_ics()
        # Attach ICS as ir.attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'steamships_booking_%s.ics' % self.name,
            'datas': ics_content.encode('utf-8'),
            'mimetype': 'text/calendar',
            'res_model': 'steamships.appointment.slot',
            'res_id': self.id,
            'type': 'binary',
        })
        template = self.env.ref(
            'steamships_demo.mail_template_booking_confirmed',
            raise_if_not_found=False)
        if not template:
            _logger.warning('Booking confirmation template not found')
            return
        try:
            template.send_mail(
                self.id, force_send=False,
                email_values={
                    'email_to': self.partner_email,
                    'attachment_ids': [(6, 0, [attachment.id])],
                })
            _logger.info('Booking confirmation email sent to %s for %s',
                         self.partner_email, self.name)
        except Exception as e:
            _logger.warning('Booking email failed: %s', e)

    def _generate_ics(self):
        """Generate ICS file content. Returns bytes string."""
        # Build event data dict
        start_local = self.start_datetime
        end_local = self.end_datetime
        png_tz = timezone(timedelta(hours=PNG_TZ_OFFSET))
        start_utc = start_local.replace(tzinfo=timezone.utc) if start_local.tzinfo is None \
            else start_local.astimezone(timezone.utc)
        end_utc = end_local.replace(tzinfo=timezone.utc) if end_local.tzinfo is None \
            else end_local.astimezone(timezone.utc)
        # Format: YYYYMMDDTHHMMSSZ
        start_str = start_utc.strftime('%Y%m%dT%H%M%SZ')
        end_str = end_utc.strftime('%Y%m%dT%H%M%SZ')
        # DTSTAMP = now in UTC
        now_utc = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        # UID
        uid = '%s@steamships.com.pg' % self.name
        summary = '%s — %s' % (
            dict(self._fields['appointment_type'].selection).get(
                self.appointment_type, 'Meeting'),
            self.partner_name)
        description = self.notes or 'Steamships appointment'
        organizer = self.assigned_user_id.email or 'sales@steamships.com.pg'
        attendee = self.partner_email
        ics = (
            'BEGIN:VCALENDAR\r\n'
            'VERSION:2.0\r\n'
            'PRODID:-//Steamships//Booking//EN\r\n'
            'CALSCALE:GREGORIAN\r\n'
            'METHOD:REQUEST\r\n'
            'BEGIN:VEVENT\r\n'
            'UID:%s\r\n'
            'DTSTAMP:%s\r\n'
            'DTSTART:%s\r\n'
            'DTEND:%s\r\n'
            'SUMMARY:%s\r\n'
            'DESCRIPTION:%s\r\n'
            'LOCATION:Steamships HQ, Port Moresby\\, PNG\r\n'
            'ORGANIZER;CN=Steamships:mailto:%s\r\n'
            'ATTENDEE;CN=%s;RSVP=TRUE:mailto:%s\r\n'
            'STATUS:CONFIRMED\r\n'
            'END:VEVENT\r\n'
            'END:VCALENDAR\r\n'
        ) % (
            uid,
            now_utc,
            start_str,
            end_str,
            _ics_escape(summary),
            _ics_escape(description),
            _ics_escape(organizer),
            _ics_escape(self.partner_name),
            _ics_escape(attendee),
        )
        return ics

    # ------------------------------------------------------------------
    # Helpers for public website
    # ------------------------------------------------------------------

    @api.model
    def get_available_slots(self, date_from, date_to, duration=30,
                             assigned_user_id=None):
        """Return list of available 30-min/60-min slots in PNG working hours.

        Returns list of dicts: {'start': datetime, 'end': datetime, 'label': str}
        """
        if not date_from or not date_to:
            return []
        # Normalize to date objects
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)
        slots = []
        current = date_from
        slot_delta = timedelta(minutes=duration)
        while current <= date_to:
            # PNG working hours: 09:00 to 17:00
            for hour in range(WORK_START_HOUR, WORK_END_HOUR):
                for minute in (0, 30):
                    slot_start = datetime.combine(
                        current, datetime.min.time()).replace(
                        hour=hour, minute=minute)
                    # For 60-min slots, ensure end fits before WORK_END_HOUR
                    if duration == 60 and minute == 30:
                        continue  # 60-min slots only on the hour
                    slot_end = slot_start + slot_delta
                    # Past slots: skip
                    if slot_start <= datetime.now():
                        continue
                    # Already booked?
                    domain = [
                        ('state', 'in', ('pending', 'confirmed')),
                        ('start_datetime', '<', slot_end),
                        ('end_datetime', '>', slot_start),
                    ]
                    if assigned_user_id:
                        domain.append(('assigned_user_id', '=',
                                       int(assigned_user_id)))
                    if not self.search_count(domain):
                        slots.append({
                            'start': slot_start,
                            'end': slot_end,
                            'label': slot_start.strftime('%H:%M'),
                            'iso': slot_start.isoformat(),
                        })
            current = current + timedelta(days=1)
        return slots

    @api.model
    def _cron_mark_past_done(self):
        """Mark confirmed appointments as 'done' 1 day after end_datetime."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        past = self.search([
            ('state', '=', 'confirmed'),
            ('end_datetime', '<', cutoff),
        ])
        if past:
            past.write({'state': 'done'})
            _logger.info('Marked %d past appointments as done', len(past))
        return True


def _ics_escape(text):
    """Escape text for ICS format (RFC 5545)."""
    if not text:
        return ''
    return (str(text)
            .replace('\\', '\\\\')
            .replace(',', '\\,')
            .replace(';', '\\;')
            .replace('\n', '\\n'))
