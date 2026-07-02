# -*- coding: utf-8 -*-
"""HTTP and JSON-RPC routes for the Steamships AI Chatbot.

* ``GET  /ask-ai``     renders the Bootstrap 5 chat page (QWeb template).
* ``POST /steamships_ai/ask`` — floating chatbot widget (returns {ok, answer, sources, chunks}).
* ``POST /ai/retrieve`` JSON-RPC bridge to the FastAPI ``ai-api`` service.

The ai-api service is reachable on the Docker network at the hostname
``ai-api`` (service name in docker-compose.yml). Port 9000 is the
container's exposed port. A ``rag-api`` network alias maintains backward
compatibility for any older configurations.
"""

import logging

from odoo import _, http

from ..services.ai_api_client import AIAPIClient, AIServiceError

_logger = logging.getLogger(__name__)

VALID_MODES = {"staff", "client"}


class SteamshipsAIController(http.Controller):
    """Chat UI + JSON-RPC proxy to the RAG retrieval API."""

    @http.route(
        "/ask-ai",
        type="http",
        auth="user",
        website=True,
        sitemap=False,
    )
    def ask_ai_page(self, **kwargs):
        """Render the chat page (Bootstrap 5 + Vanilla JS)."""
        _logger.info("Rendering Steamships AI chat page for user %s",
                     http.request.env.user.login)
        return http.request.render(
            "steamships_ai.chat_page_template",
            {
                "user_name": http.request.env.user.name or http.request.env.user.login,
                "default_mode": "STAFF",
            },
        )

    # ------------------------------------------------------------------
    # Helpers shared between the JSON-RPC endpoints
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_mode(mode):
        mode = (mode or "staff").strip().lower()
        return mode if mode in VALID_MODES else "staff"

    @staticmethod
    def _extract_chunk_value(chunk, *keys):
        if not isinstance(chunk, dict):
            return ""
        candidates = [chunk]
        metadata = chunk.get("metadata")
        if isinstance(metadata, dict):
            candidates.append(metadata)
        for candidate in candidates:
            for key in keys:
                value = candidate.get(key)
                if value:
                    return str(value).strip()
        return ""

    @classmethod
    def _extract_sources(cls, chunks):
        sources = []
        seen = set()
        for chunk in chunks or []:
            name = cls._extract_chunk_value(chunk, "doc_name", "filename", "source", "document")
            section = cls._extract_chunk_value(chunk, "section", "heading", "title")
            label = " — ".join(part for part in (name, section) if part)
            if label and label not in seen:
                seen.add(label)
                sources.append(label)
        return sources

    @classmethod
    def _format_rag_response(cls, data):
        chunks = data.get("chunks", []) or []
        sources = data.get("sources") or cls._extract_sources(chunks)
        answer = data.get("answer") or data.get("message") or ""
        if not answer and chunks:
            answer = _(
                "I found relevant document chunks, but the RAG API did not return "
                "an 'answer' field yet. Please update the API to synthesize and "
                "return an answer field for the chatbot."
            )
        elif not answer:
            answer = _("I could not find an answer for that question yet.")
        return {"ok": True, "answer": answer, "sources": sources, "chunks": chunks}

    # ------------------------------------------------------------------
    # Floating chatbot widget (POST /steamships_ai/ask)
    # ------------------------------------------------------------------
    @http.route(
        "/steamships_ai/ask",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def steamships_ai_ask(self, question=None, mode="staff", **kwargs):
        if not question or not isinstance(question, str):
            return {
                "ok": False,
                "answer": _("Please enter a question before asking the AI."),
                "sources": [],
                "chunks": [],
            }
        question = question.strip()
        if not question:
            return {
                "ok": False,
                "answer": _("Please enter a question before asking the AI."),
                "sources": [],
                "chunks": [],
            }
        if len(question) > 2000:
            question = question[:2000]

        client = AIAPIClient()
        try:
            data = client.retrieve(question, mode=self._normalise_mode(mode), top_k=8)
        except AIServiceError as exc:
            return {"ok": False, "answer": str(exc), "sources": [], "chunks": []}

        return self._format_rag_response(data)

    # ------------------------------------------------------------------
    # JSON-RPC bridge (POST /ai/retrieve) — preserved for the chat page JS
    # ------------------------------------------------------------------
    @http.route(
        "/ai/retrieve",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def ai_retrieve(self, question, mode="STAFF", **kwargs):
        if not question or not isinstance(question, str):
            return {"status": "error", "message": _("A non-empty 'question' is required.")}
        question = question.strip()
        if not question:
            return {"status": "error", "message": _("'question' cannot be whitespace only.")}
        mode = self._normalise_mode(mode)
        if len(question) > 2000:
            question = question[:2000]

        client = AIAPIClient()
        try:
            data = client.retrieve(question, mode=mode, top_k=8)
        except AIServiceError as exc:
            return {"status": "error", "message": str(exc)}

        chunks = data.get("chunks", []) or []
        answer = data.get("answer", "") or ""
        sources = data.get("sources") or self._extract_sources(chunks)
        _logger.info("AI API returned %d chunks (mode=%s, answer_len=%d)",
                     len(chunks), mode, len(answer))

        try:
            http.request.env.user.message_post(
                body=f"AI chatbot query ({mode}): {question!r} → {len(chunks)} chunks",
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        except Exception:
            _logger.exception("Failed to write chatter audit log")

        return {
            "status": "success",
            "chunks": chunks,
            "sources": sources,
            "answer": answer,
        }
