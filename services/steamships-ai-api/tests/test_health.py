"""Smoke tests for /health."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_required_shape(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "service": "steamships-ai-api"}


def test_health_does_not_require_token(client: TestClient) -> None:
    # Even with AI_API_TOKEN unset the health endpoint must answer; the
    # conftest already forces AI_API_TOKEN="" so this just confirms no auth.
    r = client.get("/health")
    assert r.status_code == 200
