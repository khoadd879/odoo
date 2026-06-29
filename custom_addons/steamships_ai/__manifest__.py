# -*- coding: utf-8 -*-
{
    "name": "Steamships AI Chatbot",
    "version": "19.0.1.0.0",
    "summary": "Day 4 — Chat UI that talks to the Steamships RAG API (rag-api:9000).",
    "description": """
Steamships AI Chatbot
=====================

Provides a website page (Ask AI) that lets authenticated Steamships staff
ask the RAG chatbot in plain language and see the top chunks returned by
the rag-api FastAPI service running on the same Docker network.

Two routes are exposed:

* ``GET  /ask-ai``  — renders the Bootstrap 5 chat UI.
* ``POST /ai/retrieve`` — JSON-RPC bridge to ``http://rag-api:9000/api/retrieve``.

The toggle between STAFF (full SOP + price-list corpus) and CLIENT
(onboarding FAQ + glossary only) is enforced server-side by rag-api via
the ``visibility`` Chroma metadata filter.
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
