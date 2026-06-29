# -*- coding: utf-8 -*-
"""HTTP and JSON-RPC routes for the Steamships AI Chatbot.

* ``GET  /ask-ai``     renders the Bootstrap 5 chat page (QWeb template).
* ``POST /ai/retrieve`` JSON-RPC bridge to the FastAPI ``rag-api`` service.

The rag-api service is reachable on the Docker network at the hostname
``rag-api`` (service name in docker-compose.yml). Port 9000 is the
container's exposed port (the host port mapping is irrelevant from
inside the compose network).
"""

import json
import logging
import os

import requests

from odoo import _, http

_logger = logging.getLogger(__name__)

# rag-api service hostname on the compose network. Override with env var so the
# same module works in CI / staging / prod without code changes.
RAG_API_BASE = os.environ.get("RAG_API_BASE", "http://rag-api:9000")
RAG_RETRIEVE_TIMEOUT = float(os.environ.get("RAG_RETRIEVE_TIMEOUT", "15"))
VALID_MODES = {"staff", "client"}


def _normalise_mode(mode):
    """Return the lowercase RAG visibility mode expected by the API."""
    mode = (mode or "staff").strip().lower()
    if mode not in VALID_MODES:
        return "staff"
    return mode


def _extract_chunk_value(chunk, *keys):
    """Extract the first non-empty value from a chunk or its metadata."""
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


def _extract_sources(chunks):
    """Build human-readable source labels from RAG chunks."""
    sources = []
    seen = set()
    for chunk in chunks or []:
        name = _extract_chunk_value(chunk, "doc_name", "filename", "source", "document")
        section = _extract_chunk_value(chunk, "section", "heading", "title")
        label = " — ".join(part for part in (name, section) if part)
        if label and label not in seen:
            seen.add(label)
            sources.append(label)
    return sources


def _format_rag_response(data):
    """Return the JSON shape consumed by the floating chatbot widget."""
    chunks = data.get("chunks", []) or []
    sources = data.get("sources") or _extract_sources(chunks)
    answer = data.get("answer") or data.get("message") or ""
    if not answer and chunks:
        answer = _(
            "I found relevant document chunks, but the RAG API did not return "
            "an 'answer' field yet. Please update the API to synthesize and "
            "return an answer field for the chatbot."
        )
    elif not answer:
        answer = _("I could not find an answer for that question yet.")
    return {
        "ok": True,
        "answer": answer,
        "sources": sources,
        "chunks": chunks,
    }


class SteamshipsAIController(http.Controller):
    """Chat UI + JSON-RPC proxy to the RAG retrieval API."""

    # ------------------------------------------------------------------ page
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

    @http.route(
        "/steamships_ai/ask",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def steamships_ai_ask(self, question=None, mode="staff", **kwargs):
        """Proxy the floating chatbot question to the RAG retrieve API."""
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

        payload = {"question": question, "mode": _normalise_mode(mode), "top_k": 8}
        url = f"{RAG_API_BASE}/api/retrieve"
        _logger.info("POST %s payload=%s", url, json.dumps(payload, ensure_ascii=False))

        try:
            upstream = requests.post(url, json=payload, timeout=RAG_RETRIEVE_TIMEOUT)
            upstream.raise_for_status()
            data = upstream.json()
        except requests.Timeout:
            _logger.exception("rag-api timeout after %.1fs", RAG_RETRIEVE_TIMEOUT)
            return {
                "ok": False,
                "answer": _("The AI service is taking too long to reply. Please try again in a moment."),
                "sources": [],
                "chunks": [],
            }
        except requests.ConnectionError:
            _logger.exception("Cannot reach rag-api at %s", url)
            return {
                "ok": False,
                "answer": _("The AI service is currently unavailable. Please check the RAG API container and try again."),
                "sources": [],
                "chunks": [],
            }
        except requests.HTTPError as exc:
            _logger.exception("rag-api HTTP error: %s", exc)
            return {
                "ok": False,
                "answer": _("The AI service returned an error. Please try again shortly."),
                "sources": [],
                "chunks": [],
            }
        except ValueError:
            _logger.exception("rag-api returned non-JSON response")
            return {
                "ok": False,
                "answer": _("The AI service returned an unexpected response."),
                "sources": [],
                "chunks": [],
            }
        except requests.RequestException as exc:
            _logger.exception("rag-api request error: %s", exc)
            return {
                "ok": False,
                "answer": _("The AI service could not be reached. Please try again later."),
                "sources": [],
                "chunks": [],
            }

        return _format_rag_response(data)

    # ------------------------------------------------------------------ json
    @http.route(
        "/ai/retrieve",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def ai_retrieve(self, question, mode="STAFF", **kwargs):
        """Forward a retrieval query to rag-api and return the chunks.

        Parameters expected by the JSON-RPC caller (Odoo JS):

        * ``question`` (str, required) — the user's natural-language query.
        * ``mode`` (str, optional)     — ``"STAFF"`` (default) or ``"CLIENT"``.
          Filtered server-side by rag-api via the ``visibility`` Chroma
          metadata — clients never see internal SOPs or pricing.

        Returns a dict shaped as::

            {"status": "success", "chunks": [{"doc_id": ..., "text": ...}, ...]}

        or, on error::

            {"status": "error", "message": "<exception message>"}
        """
        # --- 1. Validate inputs -------------------------------------------------
        if not question or not isinstance(question, str):
            return {"status": "error", "message": _("A non-empty 'question' is required.")}
        question = question.strip()
        if not question:
            return {"status": "error", "message": _("'question' cannot be whitespace only.")}
        mode = _normalise_mode(mode)
        if len(question) > 2000:
            question = question[:2000]

        # --- 2. Forward to rag-api ---------------------------------------------
        payload = {"question": question, "mode": mode, "top_k": 8}
        url = f"{RAG_API_BASE}/api/retrieve"
        _logger.info("POST %s payload=%s", url, json.dumps(payload, ensure_ascii=False))

        try:
            upstream = requests.post(url, json=payload, timeout=RAG_RETRIEVE_TIMEOUT)
        except requests.Timeout:
            _logger.exception("rag-api timeout after %.1fs", RAG_RETRIEVE_TIMEOUT)
            return {"status": "error", "message": "rag-api timeout — try again in a moment."}
        except requests.ConnectionError as exc:
            _logger.exception("rag-api connection error: %s", exc)
            return {"status": "error", "message": f"Cannot reach rag-api at {url}."}
        except requests.RequestException as exc:
            _logger.exception("rag-api request error: %s", exc)
            return {"status": "error", "message": str(exc)}

        # --- 3. Parse upstream JSON -------------------------------------------
        try:
            data = upstream.json()
        except ValueError:
            _logger.exception("rag-api returned non-JSON (status=%s body=%r)",
                              upstream.status_code, upstream.text[:300])
            return {
                "status": "error",
                "message": f"rag-api returned non-JSON (HTTP {upstream.status_code}).",
            }

        if not upstream.ok:
            _logger.error("rag-api HTTP %s: %s", upstream.status_code, data)
            return {
                "status": "error",
                "message": data.get("message") or f"rag-api HTTP {upstream.status_code}",
            }

        chunks = data.get("chunks", []) or []
        # `answer` is raw Markdown. The browser escapes first, then renders a
        # tiny safe Markdown subset for bold/headings/lists.
        answer = data.get("answer", "") or ""
        sources = data.get("sources") or _extract_sources(chunks)
        _logger.info("rag-api returned %d chunks (mode=%s, answer_len=%d)",
                     len(chunks), mode, len(answer))

        # --- 4. Audit chatter log on the calling user -------------------------
        try:
            http.request.env.user.message_post(
                body=f"AI chatbot query ({mode}): {question!r} → {len(chunks)} chunks",
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        except Exception:  # never break the response because of audit
            _logger.exception("Failed to write chatter audit log")

        return {"status": "success", "chunks": chunks, "sources": sources, "answer": answer}
