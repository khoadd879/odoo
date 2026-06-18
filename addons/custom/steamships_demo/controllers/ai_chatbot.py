"""
Steamships AI Chatbot - HTTP controller

Two modes (auto-detected at import time):
  - GROQ_API_KEY set  → call Groq Llama 3.3 70B (real LLM)
  - no key            → keyword-match mock against mock_sops

Retrieval: top-3 SOPs from `mock_sops.search_sops()` (mock RAG).
Session log: steamships.chatbot.session + steamships.chatbot.line
"""
import logging
import os

import requests

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

MODE_STAFF = 'staff'
MODE_CLIENT = 'client'
MODE_VALUES = (MODE_STAFF, MODE_CLIENT)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
GROQ_CHAT_MODEL = 'llama-3.3-70b-versatile'
GROQ_CHAT_URL = 'https://api.groq.com/openai/v1/chat/completions'

_MODE_INSTRUCTION = {
    MODE_STAFF: (
        "You are answering a Steamships staff member. "
        "You may share internal SOPs and price list data."
    ),
    MODE_CLIENT: (
        "You are answering a Steamships client (external). "
        "DO NOT reveal internal SOPs, internal policies, or exact "
        "internal prices. If asked, politely redirect to the sales team."
    ),
}


def _call_groq_chat(message, context, mode):
    """Call Groq Llama 3.3 70B. Returns reply text."""
    prompt = (
        f"You are the Steamships Trading Company (PNG) knowledge assistant.\n"
        f"{_MODE_INSTRUCTION[mode]}\n"
        f"Answer the user's question using the SOPs provided below. "
        f"Be concise (max 4 sentences) and cite sources by SOP ID. "
        f"If the SOPs don't cover the question, say so and offer to "
        f"escalate to a human.\n\n"
        f"SOPs:\n{context}\n\n"
        f"User question: {message}"
    )
    resp = requests.post(
        GROQ_CHAT_URL,
        json={
            'model': GROQ_CHAT_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.2,
            'max_tokens': 512,
        },
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['choices'][0]['message']['content'].strip()


class SteamshipsAIChatbot(http.Controller):

    @http.route('/steamships/chat/api', type='json', auth='user')
    def chat_api(self, message, mode='staff', conversation_id=None, **kw):
        if not message:
            return {'reply': 'Please type a question.', 'sources': [], 'mode': mode}

        if mode not in MODE_VALUES:
            mode = MODE_STAFF

        from ..mock_sops import search_sops

        allowed_visibility = (
            ('public', 'staff') if mode == MODE_STAFF else ('public',)
        )
        sources = search_sops(message, top_k=3, visibility=allowed_visibility)
        source_titles = [s.get('title', '?') for s in sources]
        source_ids = [s.get('id', '?') for s in sources]
        confidence = sources[0].get('confidence', 0.0) if sources else 0.0

        # Generate reply
        # Always call Groq when key is present (RAG with optional SOP context).
        # Fall back to mock ONLY when (a) no key OR (b) Groq call throws.
        groq_actually_called = False
        if GROQ_API_KEY:
            try:
                if sources:
                    context = "\n\n".join(
                        f"[{s.get('id', s.get('title', '?'))}] {s.get('title','')}\n"
                        f"{s.get('content','')}"
                        for s in sources
                    )
                else:
                    context = "(No matching SOP found in Steamships knowledge base. Answer based on general business knowledge if appropriate, or say you don't know.)"
                reply = _call_groq_chat(message, context, mode)
                mock_mode = False
                groq_actually_called = True
            except Exception as e:
                _logger.exception('Groq chat call failed, falling back to mock')
                reply = self._mock_reply(message, sources, mode)
                mock_mode = True
        else:
            reply = self._mock_reply(message, sources, mode)
            mock_mode = True

        # Persist session (best effort)
        session_id = None
        try:
            Session = request.env['steamships.chatbot.session']
            Line = request.env['steamships.chatbot.line']
            session = None
            if conversation_id:
                try:
                    session = Session.browse(int(conversation_id))
                    if not session.exists():
                        session = None
                except (ValueError, TypeError):
                    session = None
            if not session:
                session = Session.create({'mode': mode})
            session_id = session.id
            Line.create({
                'session_id': session_id,
                'role': 'user',
                'content': message,
            })
            Line.create({
                'session_id': session_id,
                'role': 'assistant',
                'content': reply,
                'source_names': ', '.join(source_ids),
            })
        except Exception as e:
            _logger.warning('Could not persist chatbot session: %s', e)

        return {
            'reply': reply,
            'sources': source_titles,
            'source_ids': source_ids,
            'confidence': confidence,
            'mode': mode,
            'mock_mode': mock_mode,
            'groq_enabled': bool(GROQ_API_KEY),
            'conversation_id': session_id,
        }

    @http.route('/steamships/chat/sessions', type='json', auth='user')
    def list_sessions(self, limit=50, **kw):
        """List recent chatbot sessions for the current user (most recent first)."""
        sessions = request.env['steamships.chatbot.session'].search(
            [], order='create_date desc', limit=int(limit),
        )
        return [{
            'id': s.id,
            'name': s.name or f"Session #{s.id}",
            'mode': s.mode,
            'create_date': s.create_date.isoformat(timespec='seconds') if s.create_date else '',
            'message_count': len(s.line_ids),
        } for s in sessions]

    @http.route('/steamships/chat/session/lines', type='json', auth='user')
    def session_lines(self, session_id, **kw):
        """Return full conversation lines for one session (read-only)."""
        try:
            sid = int(session_id)
        except (ValueError, TypeError):
            return {'error': 'invalid session_id'}
        session = request.env['steamships.chatbot.session'].browse(sid)
        if not session.exists():
            return {'error': 'session not found'}
        return {
            'id': session.id,
            'name': session.name or f"Session #{session.id}",
            'mode': session.mode,
            'create_date': session.create_date.isoformat(timespec='seconds') if session.create_date else '',
            'messages': [{
                'role': l.role,
                'content': l.content or '',
                'sources': [x.strip() for x in (l.source_names or '').split(',') if x.strip()],
                'create_date': l.create_date.isoformat(timespec='seconds') if l.create_date else '',
            } for l in session.line_ids.sorted('create_date')],
        }

    def _mock_reply(self, message, sources, mode):
        if not sources:
            if mode == MODE_CLIENT:
                return (
                    "[MOCK - CLIENT] Welcome! I can help with KYC docs, "
                    "onboarding steps, service inquiries, and contacts. "
                    "_(Set GROQ_API_KEY for real LLM.)_"
                )
            return (
                "[MOCK - STAFF] Steamships knowledge assistant. "
                "Try: 'FCL 20ft price?' or 'discount approval threshold?'. "
                "_(Set GROQ_API_KEY for real LLM.)_"
            )
        best = sources[0]
        if mode == MODE_CLIENT and (
            'pricing' in best.get('id', '').lower()
            or best.get('visibility') == 'staff'
        ):
            return (
                "[MOCK - CLIENT] That question is for staff only. "
                "Please contact our sales team."
            )
        return (
            f"[MOCK - {mode.upper()}] Based on **{best.get('title','?')}**:\n\n"
            f"{best.get('content','')}\n\n"
            f"_Source: {best.get('id', best.get('title','?'))}_"
        )
