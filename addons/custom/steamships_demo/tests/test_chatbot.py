"""Tests for chatbot session persistence."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestChatbotSession(TransactionCase):

    def test_create_session(self):
        Session = self.env['steamships.chatbot.session']
        Line = self.env['steamships.chatbot.line']

        s = Session.create({'mode': 'staff'})
        Line.create({'session_id': s.id, 'role': 'user', 'content': 'hi'})
        Line.create({'session_id': s.id, 'role': 'assistant', 'content': 'hello'})

        self.assertEqual(s.message_count, 2)

    def test_session_order_desc(self):
        Session = self.env['steamships.chatbot.session']
        s1 = Session.create({'mode': 'staff'})
        s2 = Session.create({'mode': 'staff'})
        # _order is create_date desc — s2 should come first
        recents = Session.search([], limit=2)
        self.assertEqual(recents[0].id, s2.id)
