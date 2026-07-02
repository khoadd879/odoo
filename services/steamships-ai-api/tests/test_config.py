"""Tests for the Settings loader."""

from __future__ import annotations

import os

import pytest


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_API_TOKEN", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.port == 9000
    assert settings.chroma_path == "/data/chroma"
    assert settings.collection_name == "steamships_rag"
    assert settings.chunk_size == 800
    assert settings.chunk_overlap == 100
    assert settings.top_k == 5
    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.ai_api_token == ""  # empty -> no auth required
    assert settings.allowed_origins == []


def test_settings_load_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
    monkeypatch.setenv("PORT", "9100")
    monkeypatch.setenv("TOP_K", "10")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8069,http://localhost:9000")

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.ai_api_token == "secret-token"
    assert settings.port == 9100
    assert settings.top_k == 10
    assert settings.allowed_origins == [
        "http://localhost:8069",
        "http://localhost:9000",
    ]
