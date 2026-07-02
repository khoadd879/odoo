"""Auth-required tests for the protected POST endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client(monkeypatch: pytest.MonkeyPatch):
    """TestClient with AI_API_TOKEN forced to 'secret'."""
    # Set ALL env vars explicitly so no cross-test pollution.
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/steamships-test-chroma")
    monkeypatch.setenv("DOCS_PATH", "/tmp/steamships-test-docs")
    monkeypatch.setenv("MANIFEST_PATH", "/tmp/steamships-test-manifest.json")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    # Bust the cached settings so the dependency reads the new value.
    from app import config
    config.get_settings.cache_clear()
    # Re-import main so its module-level Settings cache (if any) is fresh.
    from app.main import app

    with TestClient(app) as client:
        yield client


def test_retrieve_without_token_returns_401(auth_client: TestClient) -> None:
    r = auth_client.post("/api/retrieve", json={"question": "hi", "mode": "staff"})
    assert r.status_code == 401


def test_retrieve_with_wrong_token_returns_401(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/api/retrieve",
        json={"question": "hi", "mode": "staff"},
        headers={"X-AI-Token": "nope"},
    )
    assert r.status_code == 401


def test_retrieve_with_correct_token_is_accepted_shape(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stub the underlying query so we don't need a real model.
    from app.rag import retrieve as retrieve_mod

    def fake_query_chunks(*_args, **_kwargs):
        return []

    monkeypatch.setattr(retrieve_mod, "query_chunks", fake_query_chunks)
    # Stub the LLM call to avoid touching OpenAI — patch on the module.
    from app import main as main_mod

    monkeypatch.setattr(
        main_mod,
        "_synthesise_answer",
        lambda *_args, **_kwargs: "stub answer",
    )

    r = auth_client.post(
        "/api/retrieve",
        json={"question": "What is the price?", "mode": "staff"},
        headers={"X-AI-Token": "secret-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "stub answer"
    assert body["sources"] == []
    assert body["chunks"] == []


def test_bearer_token_also_works(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/api/retrieve",
        json={"question": "x", "mode": "client"},
        headers={"Authorization": "Bearer secret-token"},
    )
    # 200 expected when the query/LLM are stubbed by other tests; if this
    # test runs in isolation we accept either a 200 (stub) or 500 (real LLM
    # path) but never 401.
    assert r.status_code != 401
