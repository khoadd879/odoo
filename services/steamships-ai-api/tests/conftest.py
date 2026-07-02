"""Shared pytest fixtures for the steamships-ai-api test suite."""

from __future__ import annotations

import os
import sys
import types
import tempfile
import shutil
from typing import Iterator

import pytest


# ---------------------------------------------------------------------------
# Stub fixtures — must be configured before any module imports
# sentence_transformers / chromadb / openai / python_multipart.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid downloading the embedding model during the test session."""
    import numpy as np

    class _FakeModel:
        def encode(self, *args, **kwargs):
            arr = np.zeros((len(args[0]) if args else 1, 4), dtype="float32")
            return arr

    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = lambda *_a, **_k: _FakeModel()
    sys.modules["sentence_transformers"] = fake


@pytest.fixture(autouse=True)
def _stub_chromadb(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stub chromadb so PersistentClient and Collection work without the package."""
    if "chromadb" in sys.modules:
        yield
        return

    tmp = tempfile.mkdtemp(prefix="chromadb_stub_")

    os.makedirs(os.path.join(tmp, "chromadb"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "chromadb", "api"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "chromadb", "api", "models"), exist_ok=True)

    with open(os.path.join(tmp, "chromadb", "__init__.py"), "w") as fh:
        fh.write("")
    with open(os.path.join(tmp, "chromadb", "api", "__init__.py"), "w") as fh:
        fh.write("")
    with open(os.path.join(tmp, "chromadb", "api", "models", "__init__.py"), "w") as fh:
        fh.write("")

    class _FakeCollection:
        def count(self):
            return 0

        def query(self, **kwargs):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        def upsert(self, **kwargs):
            pass

    sys.modules["chromadb.api.models.Collection"] = types.ModuleType("chromadb.api.models.Collection")
    sys.modules["chromadb.api.models.Collection"].Collection = _FakeCollection

    api_models = types.ModuleType("chromadb.api.models")
    api_models.Collection = _FakeCollection
    sys.modules["chromadb.api.models"] = api_models

    api = types.ModuleType("chromadb.api")
    api.models = api_models
    sys.modules["chromadb.api"] = api

    fake_root = types.ModuleType("chromadb")
    fake_root.api = api

    class _FakeClient:
        def get_or_create_collection(self, *args, **kwargs):
            return _FakeCollection()

    fake_root.PersistentClient = lambda *a, **k: _FakeClient()
    sys.modules["chromadb"] = fake_root

    sys.path.insert(0, tmp)

    yield

    shutil.rmtree(tmp, ignore_errors=True)
    if tmp in sys.path:
        sys.path.remove(tmp)


@pytest.fixture(autouse=True)
def _stub_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub openai so `from openai import OpenAI` succeeds without the package."""
    if "openai" in sys.modules:
        return

    class _FakeCompletion:
        choices = [type("msg", (), {"message": type("m", (), {"content": "stub"})()})()]

    class _FakeChatCompletions:
        def create(self, *args, **kwargs):
            return _FakeCompletion()

    class _FakeChat:
        @property
        def completions(self):
            return _FakeChatCompletions()

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def chat(self):
            return _FakeChat()

    sys.modules["openai"] = types.ModuleType("openai")
    sys.modules["openai"].OpenAI = _FakeOpenAI


@pytest.fixture(autouse=True)
def _stub_python_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub python_multipart so FastAPI file uploads work without the package."""
    if "multipart" in sys.modules or "python_multipart" in sys.modules:
        return

    # Provide a minimal parse_options_header that returns a usable tuple.
    def _fake_parse_options_header(value, *args, **kwargs):
        return ("application/octet-stream", {})

    m = types.ModuleType("multipart")
    m.parse_options_header = _fake_parse_options_header
    sys.modules["multipart"] = m

    pm = types.ModuleType("python_multipart")
    pm.parse_options_header = _fake_parse_options_header
    sys.modules["python_multipart"] = pm


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> Iterator:
    """Yield a TestClient bound to the FastAPI app.

    We import lazily so each test can set env vars before Settings() loads.
    """
    os.environ["AI_API_TOKEN"] = ""
    os.environ["CHROMA_PATH"] = "/tmp/steamships-test-chroma"
    os.environ["DOCS_PATH"] = "/tmp/steamships-test-docs"
    os.environ["MANIFEST_PATH"] = "/tmp/steamships-test-manifest.json"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["OPENAI_BASE_URL"] = ""
    os.environ["OPENAI_MODEL"] = "test-model"
    os.environ["EMBEDDING_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"

    # Bust any cached settings from a previous test that set AI_API_TOKEN.
    from app.config import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from app.main import app  # lazy import after env is set

    with TestClient(app) as test_client:
        yield test_client
