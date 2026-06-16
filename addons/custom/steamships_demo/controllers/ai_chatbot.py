"""
Steamships AI Chatbot - HTTP controller (MOCK MODE)

Adapter pattern: real Claude API can swap in by setting
ANTHROPIC_API_KEY env var. Without it, returns canned answers
from a small SOP knowledge base (15 entries in mock_sops.py).

Exposed as Odoo backend menu action "Steamships AI Assistant" (not a
website page). Staff opens it from the main menu; render happens in
the Odoo backend (web.assets_backend) so the chat history stays in
the Odoo session, not the public website.
"""
import json
import logging
import os

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# Mode constants (per DOCX B4: STAFF vs CLIENT)
MODE_STAFF = 'staff'
MODE_CLIENT = 'client'
MODE_VALUES = (MODE_STAFF, MODE_CLIENT)


class SteamshipsAIChatbot(http.Controller):
    MOCK_MODE = not os.environ.get('ANTHROPIC_API_KEY')

    # --- Chat endpoint (JSON-RPC, backend-authenticated) ---

    @http.route('/steamships/chat/api', type='json', auth='user')
    def chat_api(self, message, mode='staff', conversation_id=None, **kw):
        """Process a chat message and return a reply.

        Args:
            message: user question (str)
            mode: 'staff' (full SOPs + prices) or 'client' (FAQ only)
            conversation_id: optional Odoo thread id for logging

        Real LLM path (when ANTHROPIC_API_KEY set):
            1. Retrieve top-k relevant SOPs from kb (BM25 or pgvector)
            2. Build prompt with context (mode-filtered)
            3. Call anthropic.messages.create()
            4. Return text + sources

        Mock path (no key): keyword match against mock_sops, mode-filtered.
        """
        if not message:
            return {'reply': 'Please type a question.', 'sources': [], 'mode': mode}

        if mode not in MODE_VALUES:
            mode = MODE_STAFF

        from ..mock_sops import search_sops

        # Mode-aware retrieval: client mode filters out SOPs/prices
        allowed_visibility = (
            ('public', 'staff') if mode == MODE_STAFF else ('public',)
        )
        sources = search_sops(message, top_k=3, visibility=allowed_visibility)

        if self.MOCK_MODE:
            reply = self._mock_reply(message, sources, mode)
        else:
            reply = self._real_llm_reply(message, sources, mode)

        # Log to chatter if linked to a record (best effort)
        if conversation_id:
            try:
                rec = request.env[conversation_id.split(',')[0]].browse(
                    int(conversation_id.split(',')[1]))
                rec.message_post(
                    body=f'[AI Chat ({mode})] Q: {message}\nA: {reply}',
                    subtype_xmlid='mail.mt_note')
            except Exception as e:
                _logger.warning('Could not log AI chat to chatter: %s', e)

        return {
            'reply': reply,
            'sources': [s['title'] for s in sources],
            'mode': mode,
            'mock_mode': self.MOCK_MODE,
        }

    # --- Helpers ---

    def _mock_reply(self, message, sources, mode):
        if not sources:
            if mode == MODE_CLIENT:
                return (
                    "[MOCK MODE - CLIENT] I'm a client onboarding helper. "
                    "I can help with: KYC documents, registration steps, "
                    "what to expect next. Try asking 'What documents do I need to onboard?' "
                    "(Set ANTHROPIC_API_KEY env var to enable real LLM.)"
                )
            return (
                "[MOCK MODE - STAFF] I'm a demo assistant for Steamships staff. "
                "I can answer questions about: divisions, FCL/LCL pricing, "
                "KYC requirements, discount approval rules. "
                "Try asking 'What is FCL 20ft price?' or 'What documents do I need?' "
                "(Set ANTHROPIC_API_KEY env var to enable real LLM.)"
            )
        best = sources[0]
        # In client mode, never expose prices or SOP numbers
        if mode == MODE_CLIENT and (
            'pricing' in best.get('id', '').lower()
            or best.get('visibility') == 'staff'
        ):
            return (
                "[MOCK MODE - CLIENT] That question is for staff only. "
                "Please contact our sales team for pricing or internal SOPs."
            )
        return (
            f"[MOCK MODE - {mode.upper()}] Based on **{best['title']}**:\n\n"
            f"{best['content']}\n\n"
            f"_Source: {best['title']}_"
        )

    def _real_llm_reply(self, message, sources, mode):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
            context = "\n\n".join(
                f"[{s['title']}]\n{s['content']}" for s in sources
            )
            mode_instruction = {
                MODE_STAFF: (
                    "You are answering a Steamships staff member. "
                    "You may share internal SOPs and price list data."
                ),
                MODE_CLIENT: (
                    "You are answering a Steamships client (external). "
                    "DO NOT reveal internal SOPs, internal policies, or exact "
                    "internal prices. If asked, politely redirect to the sales team."
                ),
            }[mode]
            prompt = f"""You are the Steamships Trading Company (PNG) knowledge assistant.
{mode_instruction}
Answer the user's question using the SOPs provided below. Be concise and cite sources.
If the SOPs don't cover the question, say so and offer to escalate to a human.

SOPs:
{context}

User question: {message}"""
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            _logger.exception("Real LLM call failed")
            return f"AI service error: {e}"
