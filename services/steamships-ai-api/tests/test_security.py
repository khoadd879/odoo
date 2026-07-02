"""Tests for the AI_API_TOKEN auth dependency."""

from __future__ import annotations

import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def fresh_app(monkeypatch: pytest.MonkeyPatch):
    """Build a tiny FastAPI app that uses require_token as a dependency.

    We rebuild the app per test to ensure settings reload after env changes.
    """
    from app import security

    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    return app


def test_no_token_set_allows_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "")
    from app import security
    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/protected")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_token_set_rejects_missing_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    from app import security
    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/protected")
    assert r.status_code == 401
    assert "token" in r.json().get("detail", "").lower()


def test_token_set_rejects_wrong_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    from app import security
    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/protected", headers={"X-AI-Token": "wrong"})
    assert r.status_code == 401


def test_token_set_accepts_correct_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    from app import security
    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/protected", headers={"X-AI-Token": "secret-token"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_token_set_accepts_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    from app import security
    security.get_settings.cache_clear()

    app = FastAPI()

    @app.post("/protected")
    def protected(_=Depends(security.require_token)):
        return {"ok": True}

    client = TestClient(app)
    r = client.post(
        "/protected",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert r.status_code == 200
