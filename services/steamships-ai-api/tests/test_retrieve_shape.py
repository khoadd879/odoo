"""Verify /api/retrieve always returns the {answer, sources, chunks} shape.

These tests deliberately do NOT stub the LLM — they confirm that even when
no model is configured and no API key is set, the endpoint returns a clean
JSON shape with an explanatory answer instead of a 500 stack trace.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_retrieve_no_key_returns_clean_shape(client: TestClient) -> None:
    # Ensure no API key is set so we exercise the "LLM unavailable" branch.
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["GROQ_API_KEY"] = ""
    os.environ["OPENAI_BASE_URL"] = ""

    r = client.post(
        "/api/retrieve",
        json={"question": "price of 20ft Lae to POM", "mode": "staff"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"answer", "sources", "chunks"}
    assert isinstance(body["answer"], str)
    assert isinstance(body["sources"], list)
    assert isinstance(body["chunks"], list)
    # When the LLM is missing we surface a clear error string, not a crash.
    assert body["answer"]
