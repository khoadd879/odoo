# -*- coding: utf-8 -*-
{
    "name": "Steamships AI Chatbot",
    "version": "19.0.1.1.0",
    "summary": "Chat UI that talks to the steamships-ai-api service (ai-api:9000).",
    "description": """
Steamships AI Chatbot
=====================

Provides a website page (Ask AI) that lets authenticated Steamships staff
ask the RAG chatbot in plain language and see the top chunks returned by
the steamships-ai-api FastAPI service.

Two routes are exposed:

* ``GET  /ask-ai``  — renders the Bootstrap 5 chat UI.
* ``POST /steamships_ai/ask`` — floating chatbot widget (returns {ok, answer, sources, chunks}).
* ``POST /ai/retrieve`` — JSON-RPC bridge to ``http://ai-api:9000/api/retrieve``.

Auth is enforced server-side by ai-api via the ``X-AI-Token`` header when
``AI_API_TOKEN`` is configured. The toggle between STAFF and CLIENT visibility
is enforced via the ``visibility`` Chroma metadata filter.

Env vars on the Odoo service:
* ``RAG_API_BASE`` — base URL of the AI API (default http://ai-api:9000).
* ``OCR_API_BASE`` — base URL for OCR endpoints (default http://ai-api:9000).
* ``AI_API_TOKEN`` — shared secret with the AI API (optional; enables auth).
* ``RAG_RETRIEVE_TIMEOUT`` — request timeout in seconds (default 15).
""",
    "author": "Steamships Prototype Team",
    "website": "https://steamships.com.pg",
    "category": "Website / AI",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "website",
    ],
    "data": [
        "views/chat_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "steamships_ai/static/src/js/chatbot_widget.js",
            "steamships_ai/static/src/scss/chatbot_widget.scss",
        ],
        "web.assets_frontend": [
            "steamships_ai/static/src/js/chatbot_widget.js",
            "steamships_ai/static/src/scss/chatbot_widget.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
