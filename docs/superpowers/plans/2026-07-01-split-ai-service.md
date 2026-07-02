# Split AI Service (RAG + OCR) Out of Odoo Repo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-KILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the existing `rag/` RAG service into a stand-alone, independently deployable FastAPI service named `steamships-ai-api`, while preserving all existing local-Docker workflows for the Odoo repo. The Odoo `steamships_ai` and `steamships_document_ai` modules continue to call the AI API over HTTP, configured via env vars (`RAG_API_BASE`, `OCR_API_BASE`, `AI_API_TOKEN`).

**Architecture:**

```
+-----------------------+         +-----------------------------+         +---------------------+
|  Odoo container       |  HTTP   |  steamships-ai-api container|  SDK    |  External LLM       |
|  steamships_ai        | ------->|  FastAPI (port 9000)        | ------->|  Groq / OpenAI etc. |
|  steamships_document_ai         |  /api/retrieve              |         +---------------------+
|  (proxy + UI)         | ------->|  /api/ocr/bill-of-lading    | ----+
|                       | ------->|  /api/ocr/invoice           | ----|  OCR/Vision LLM
|                       | ------->|  /api/ingest/rebuild        |     |  (Gemini, etc.)
+-----------------------+  X-AI-  +-----------------------------+     |
                              Token|                                  |
                                    v                                  v
                                  Chroma (./chroma_data)            Local files
                                  (PersistentClient)                (./mock_data)
```

In dev, everything runs in one `docker compose` project on a shared network.
In prod, Odoo runs on OEC and `steamships-ai-api` runs separately on Railway/Render/VPS; Odoo calls it over HTTPS via `RAG_API_BASE` / `OCR_API_BASE`.

**Tech Stack:** FastAPI 0.115+, uvicorn[standard], pydantic v2, pydantic-settings, python-multipart, requests (Odoo side), ChromaDB 0.5.x, sentence-transformers (default embedding), OpenAI client (Groq-compatible), PyMuPDF (optional), pytest+httpx for tests. No change to Odoo version (19.0). No change to `steamships_ai` response shape.

---

## Execution notes

- The user instructions say "no push until local tests pass" — **do not push or open a PR until tasks 17–18 pass locally**.
- **Do not delete the legacy `rag/` folder.** Move it to `legacy/rag/` at the end and add a `legacy/README.md` redirect note. Same for `rag/app/` scripts — keep them runnable.
- **Do not change `services/document_ai_api/`** in this plan; the existing OCR service is left as-is. We only add new endpoints in `services/steamships-ai-api/` that mirror the same shape, so that the OCR service can be merged later.
- The old `rag-api` service in `docker-compose.yml` will be **renamed to `ai-api`**. To stay backward-compatible with any local code referencing `http://rag-api:9000`, the new `ai-api` service gets a `networks` alias `rag-api`. Docker compose supports `networks: { default: { aliases: [rag-api] } }` so existing code keeps working.
- **No real secrets in any committed file.** `.env.example` uses `change-me-...` placeholders. `.env` is gitignored.
- The plan uses `TDD` order (test first, then implementation, then run, then optional commit) for every FastAPI endpoint, security helper, and Odoo client.

---

## File structure

### New files (steamships-ai-api service)

```
services/
└── steamships-ai-api/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py             # FastAPI app, lifespan, route wiring
    │   ├── config.py           # pydantic-settings Settings
    │   ├── security.py         # AI_API_TOKEN dependency + X-AI-Token header
    │   ├── rag/
    │   │   ├── __init__.py
    │   │   ├── ingest.py       # moved from rag/app/ingest.py
    │   │   ├── retrieve.py     # moved from rag/app/retrieve.py
    │   │   ├── prompts.py      # NEW — extracted system prompts
    │   │   ├── schemas.py      # moved from rag/app/schemas.py
    │   │   └── manifest.py     # moved from rag/app/manifest.py
    │   └── ocr/
    │       ├── __init__.py
    │       ├── bill_of_lading.py  # stub returning required JSON shape
    │       ├── invoice.py         # stub returning status=not_implemented
    │       └── schemas.py         # Pydantic models for OCR responses
    ├── tests/
    │   ├── __init__.py
    │   ├── conftest.py
    │   └── test_health.py
    ├── Dockerfile
    ├── requirements.txt
    ├── .env.example
    └── README.md
```

### Modified files

- `docker-compose.yml` — rename `rag-api` → `ai-api` (with `rag-api` network alias), change `build.context` → `services/steamships-ai-api`, add `ai_api_client.py`-friendly env vars on `odoo` service.
- `.env.example` — add AI API + RAG env block (without secrets).
- `.gitignore` — add `uploads/`, `*.pdf`, `*.png`, `*.jpg`, `*.jpeg` (per requirement 16).
- `README.md` — architecture + local-run + curl examples + deployment notes.
- `custom_addons/steamships_ai/controllers/main.py` — switch default base URL to `http://ai-api:9000`, add `AI_API_TOKEN` env support, send `X-AI-Token` header when set, error-message tightening.

### Moved files (kept runnable)

- `rag/` → `legacy/rag/` (with `legacy/rag/README.md` redirect).
- `rag/app/scripts/seed.py` → `legacy/rag/scripts/seed.py` (path-rewrite to `/data/chroma` etc.).
- `rag/app/scripts/smoke_query.py` → `legacy/rag/scripts/smoke_query.py`.

### New Odoo helper (small, additive)

- `custom_addons/steamships_ai/services/__init__.py`
- `custom_addons/steamships_ai/services/ai_api_client.py` — single helper class `AIAPIClient` with `retrieve()` and `ocr_bill_of_lading(file_bytes, filename, mimetype)` methods, used by the controller. Sends `X-AI-Token` if env is set. No business logic.

### New tests

- `services/steamships-ai-api/tests/test_health.py` — `/health` always 200, returns required JSON shape.
- `services/steamships-ai-api/tests/test_auth.py` — `/api/retrieve` returns 401 when `AI_API_TOKEN` set and `X-AI-Token` missing.
- `services/steamships-ai-api/tests/test_retrieve_shape.py` — `/api/retrieve` returns `{answer, sources, chunks}` (empty arrays if no corpus) without crashing on missing model / API key.
- `services/steamships-ai-api/tests/test_ocr_shape.py` — `/api/ocr/bill-of-lading` returns the required strict JSON shape; `/api/ocr/invoice` returns `status: not_implemented` without crashing.

---

## Task ordering

Tasks 1–4 lay the scaffold and write the failing tests first. Tasks 5–10 implement the FastAPI endpoints. Tasks 11–12 wire Odoo. Tasks 13–14 update Docker/local-run config. Tasks 15–16 docs + cleanup. Task 17 is local verification. Task 18 is delivery summary.

---

### Task 1: Create branch + scaffold services/steamships-ai-api/

**Files:**

- Create: `services/steamships-ai-api/app/__init__.py` (empty)
- Create: `services/steamships-ai-api/tests/__init__.py` (empty)
- Create: `services/steamships-ai-api/app/rag/__init__.py` (empty)
- Create: `services/steamships-ai-api/app/ocr/__init__.py` (empty)
- Create: `services/steamships-ai-api/tests/conftest.py`
- Create: `services/steamships-ai-api/.env.example`

- [ ] **Step 1: Create the branch**

```bash
cd /home/khoa/Company/odoo
git checkout -b split-ai-service
```

Expected: `Switched to a new branch 'split-ai-service'`.

- [ ] **Step 2: Create the directory tree and empty `__init__.py` files**

```bash
mkdir -p services/steamships-ai-api/app/rag
mkdir -p services/steamships-ai-api/app/ocr
mkdir -p services/steamships-ai-api/tests
touch services/steamships-ai-api/app/__init__.py
touch services/steamships-ai-api/app/rag/__init__.py
touch services/steamships-ai-api/app/ocr/__init__.py
touch services/steamships-ai-api/tests/__init__.py
```

- [ ] **Step 3: Write `conftest.py`**

Create `services/steamships-ai-api/tests/conftest.py`:

```python
"""Shared pytest fixtures for the steamships-ai-api test suite."""

from __future__ import annotations

import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Yield a TestClient bound to the FastAPI app.

    We import lazily so each test can set env vars before Settings() loads.
    """
    # Force-disable the AI_API_TOKEN for the /health-focused tests; auth tests
    # override this explicitly. The default empty value means no token is
    # required, matching local dev with no auth configured.
    os.environ.setdefault("AI_API_TOKEN", "")
    # Disable real Chroma initialisation in tests — we stub the lifespan out
    # by setting CHROMA_PATH to a temp path that won't be touched unless the
    # test exercises ingest.
    os.environ.setdefault("CHROMA_PATH", "/tmp/steamships-test-chroma")
    os.environ.setdefault("DOCS_PATH", "/tmp/steamships-test-docs")
    os.environ.setdefault("MANIFEST_PATH", "/tmp/steamships-test-manifest.json")
    os.environ.setdefault("OPENAI_API_KEY", "")
    os.environ.setdefault("OPENAI_BASE_URL", "")
    os.environ.setdefault("OPENAI_MODEL", "test-model")
    os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    from app.main import app  # lazy import after env is set

    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 4: Write `.env.example` for the new service**

Create `services/steamships-ai-api/.env.example`:

```bash
# steamships-ai-api — local development env (DO NOT COMMIT real values)

PORT=9000

# Auth — leave empty for local dev (no token required).
# In production set this to a long random string; share it with Odoo via
# the Odoo service's AI_API_TOKEN env var.
AI_API_TOKEN=

# Vector store
VECTOR_BACKEND=chroma
CHROMA_PATH=/data/chroma
COLLECTION_NAME=steamships_rag
DOCS_PATH=/docs/mock/rag_documents
MANIFEST_PATH=/docs/mock/rag_documents/MANIFEST_ingestion_metadata.json

# Chunking
CHUNK_SIZE=800
CHUNK_OVERLAP=100
TOP_K=5

# Embedding model (downloaded by sentence-transformers on first call)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# LLM (OpenAI-compatible; Groq is the default backend)
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
GROQ_API_KEY=

# OCR — left blank until we wire the OCR service in.
OCR_MODEL=

# CORS — comma-separated origins, or empty to disable.
ALLOWED_ORIGINS=
```

- [ ] **Step 5: Verify the directory tree**

Run:
```bash
find services/steamships-ai-api -type f | sort
```

Expected:
```
services/steamships-ai-api/.env.example
services/steamships-ai-api/app/__init__.py
services/steamships-ai-api/app/ocr/__init__.py
services/steamships-ai-api/app/rag/__init__.py
services/steamships-ai-api/tests/__init__.py
services/steamships-ai-api/tests/conftest.py
```

---

### Task 2: Write `app/config.py` using pydantic-settings

**Files:**

- Create: `services/steamships-ai-api/app/config.py`
- Test: `services/steamships-ai-api/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `services/steamships-ai-api/tests/test_config.py`:

```python
"""Tests for the Settings loader."""

from __future__ import annotations

import os

import pytest


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_API_TOKEN", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    from app.config import get_settings

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

    settings = get_settings()
    assert settings.ai_api_token == "secret-token"
    assert settings.port == 9100
    assert settings.top_k == 10
    assert settings.allowed_origins == [
        "http://localhost:8069",
        "http://localhost:9000",
    ]
```

- [ ] **Step 2: Run the test — expect import error**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `services/steamships-ai-api/app/config.py`:

```python
"""Runtime configuration for the steamships-ai-api FastAPI service.

All values come from environment variables so the same image runs unchanged
locally (docker compose), on Railway/Render, and on a VPS. pydantic-settings
keeps the load order predictable and gives type coercion + validation for
free.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable snapshot of the runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    port: int = Field(default=9000, ge=1, le=65535)

    # Auth — empty means no token required (local dev default).
    ai_api_token: str = Field(default="", alias="AI_API_TOKEN")

    # Vector store
    vector_backend: str = Field(default="chroma", alias="VECTOR_BACKEND")
    chroma_path: str = Field(default="/data/chroma", alias="CHROMA_PATH")
    collection_name: str = Field(default="steamships_rag", alias="COLLECTION_NAME")
    docs_path: str = Field(
        default="/docs/mock/rag_documents", alias="DOCS_PATH"
    )
    manifest_path: str = Field(
        default="/docs/mock/rag_documents/MANIFEST_ingestion_metadata.json",
        alias="MANIFEST_PATH",
    )

    # Chunking / retrieval
    chunk_size: int = Field(default=800, ge=64, le=4000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, ge=0, le=1000, alias="CHUNK_OVERLAP")
    top_k: int = Field(default=5, ge=1, le=20, alias="TOP_K")

    # Embedding
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )

    # LLM (OpenAI-compatible; Groq is the default backend).
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="", alias="OPENAI_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    # OCR
    ocr_model: str = Field(default="", alias="OCR_MODEL")

    # CORS — comma-separated.
    allowed_origins: List[str] = Field(default_factory=list, alias="ALLOWED_ORIGINS")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):  # type: ignore[override]
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [item.strip() for item in str(value).split(",") if item.strip()]

    @property
    def auth_required(self) -> bool:
        """True when AI_API_TOKEN is configured — endpoints must enforce it."""
        return bool(self.ai_api_token)

    @property
    def llm_api_key(self) -> str:
        """Resolve the effective API key for the LLM client (OPENAI > GROQ)."""
        return self.openai_api_key or self.groq_api_key

    @property
    def llm_base_url(self) -> str:
        """Default to Groq when OPENAI_BASE_URL is unset."""
        return self.openai_base_url or "https://api.groq.com/openai/v1"

    @property
    def llm_model(self) -> str:
        """Default to the Groq llama-3.3 70B when OPENAI_MODEL is unset."""
        return self.openai_model or "llama-3.3-70b-versatile"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Tests that need fresh values should clear the cache with
    ``get_settings.cache_clear()`` after patching the environment.
    """
    return Settings()
```

- [ ] **Step 4: Run the test — expect PASS**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Install pydantic-settings into the dev env (outside the image)**

Run:
```bash
pip install pydantic-settings
```

Expected: installs successfully.

---

### Task 3: Write `app/security.py` — token dependency

**Files:**

- Create: `services/steamships-ai-api/app/security.py`
- Test: `services/steamships-ai-api/tests/test_security.py`

- [ ] **Step 1: Write the failing test**

Create `services/steamships-ai-api/tests/test_security.py`:

```python
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
```

- [ ] **Step 2: Run the test — expect import error**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/test_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.security'`.

- [ ] **Step 3: Implement `app/security.py`**

Create `services/steamships-ai-api/app/security.py`:

```python
"""Auth helper for the steamships-ai-api FastAPI service.

Behaviour:
- When AI_API_TOKEN is empty (local dev default), no token is required.
- When AI_API_TOKEN is set, every protected endpoint must include one of:
    X-AI-Token: <token>
    Authorization: Bearer <token>
  Mismatch / missing -> HTTP 401 with a generic detail message that does NOT
  echo the configured token.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from .config import Settings, get_settings


def _extract_token(
    x_ai_token: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    """Pull the token from X-AI-Token or Authorization: Bearer headers."""
    if x_ai_token:
        return x_ai_token.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def require_token(
    x_ai_token: Optional[str] = Header(default=None, alias="X-AI-Token"),
    authorization: Optional[str] = Header(default=None),
    settings: Settings = None,  # type: ignore[assignment]
) -> None:
    """FastAPI dependency that enforces AI_API_TOKEN when configured.

    Returns nothing on success. Raises HTTP 401 on missing/wrong token.
    """
    if settings is None:
        settings = get_settings()
    if not settings.auth_required:
        return  # auth disabled

    presented = _extract_token(x_ai_token, authorization)
    if presented is None or presented != settings.ai_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid AI API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

- [ ] **Step 4: Run the test — expect PASS**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/test_security.py -v
```

Expected: 5 passed.

---

### Task 4: Move existing RAG code into `app/rag/`

**Files:**

- Move: `rag/app/config.py` → `services/steamships-ai-api/app/rag/config_compat.py` (then delete `config_compat.py` once we wire through `app.config`)
- Move: `rag/app/schemas.py` → `services/steamships-ai-api/app/rag/schemas.py`
- Move: `rag/app/manifest.py` → `services/steamships-ai-api/app/rag/manifest.py`
- Move: `rag/app/ingest.py` → `services/steamships-ai-api/app/rag/ingest.py`
- Move: `rag/app/retrieve.py` → `services/steamships-ai-api/app/rag/retrieve.py`

- [ ] **Step 1: Copy the files into the new layout**

```bash
SRC=rag/app
DST=services/steamships-ai-api/app/rag
cp "$SRC/schemas.py"   "$DST/schemas.py"
cp "$SRC/manifest.py"  "$DST/manifest.py"
cp "$SRC/ingest.py"    "$DST/ingest.py"
cp "$SRC/retrieve.py"  "$DST/retrieve.py"
```

- [ ] **Step 2: Patch imports**

Edit `services/steamships-ai-api/app/rag/ingest.py`:
- Replace `from .config import` with `from ..config import` everywhere.
- Replace `from .manifest import Manifest` (already relative, stays correct).

Edit `services/steamships-ai-api/app/rag/retrieve.py`:
- Replace `from .ingest import Chunk` with `from .ingest import Chunk`.
- Replace `from .schemas import RetrievedChunk` with `from .schemas import RetrievedChunk`.

- [ ] **Step 3: Confirm files compile**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -c "from app.rag import ingest, retrieve, schemas, manifest; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Leave legacy `rag/` in place**

Do **not** delete `rag/` yet — Task 16 handles moving it to `legacy/rag/`.

---

### Task 5: Extract prompts into `app/rag/prompts.py`

**Files:**

- Create: `services/steamships-ai-api/app/rag/prompts.py`

- [ ] **Step 1: Create the prompts module**

Create `services/steamships-ai-api/app/rag/prompts.py`:

```python
"""System prompts used by the retrieve endpoint.

Extracted from the previous monolithic main.py so they live next to the rest
of the RAG code. The structure mirrors the Day 4 chatbot contract: a base
prompt + per-mode variants. Behaviour must stay identical to avoid breaking
the chatbot widget's Markdown rendering.
"""

from __future__ import annotations

BASE_SYSTEM_PROMPT = """
You are a friendly and professional AI Assistant for Steamships Trading Company.

Rules:
- Answer in the same language as the user.
- Answer only from the supplied Context.
- If the answer is not in Context, reply exactly:
  I don't know based on the available documents. Please ask the Sales Operations team.
- Do not guess, invent prices, invent documents, or invent approvals.
- Keep answers short, clear, and demo-ready.
- Return plain Markdown only. Do not return HTML.
- For every specific business answer, use Markdown headings and bullets/lists. Avoid long paragraphs.
- Use `**bold**` for important facts: prices, routes, container types, mode, warnings, approval rules, and source names.
- For quote/document questions, use exactly these headings and no substitutes: `### Quote Guidance`, `### Required Documents`, `### Odoo Next Step`, `### Sources`.
- Do not add alternative headings such as `### Shipping Process` or `### Next Steps`.
"""

CLIENT_SYSTEM_PROMPT = """
You are answering in **CLIENT mode**.
**Do not reveal internal pricing**, internal SOP names/details, margins, discount limits, pricelist names, or approval rules.
If the client asks for internal/demo pricing, margins, SOPs, discounts, or approvals, say they need to contact Sales for an official quote.
Only use public/client-safe context.
For shipping quote/document questions, use this safe structure:

### Quote Guidance
- Service: **20ft FCL, Lae → Port Moresby**
- Price: Please contact **Sales** for an official quote.

### Required Documents
**Client onboarding**
1. Registration form
2. KYC documents
3. Signed terms

**Container booking**
1. Commercial invoice
2. Packing list
3. Export permit, if applicable
4. Shipper and consignee details
5. Commodity, weight, volume, container type and quantity

### Odoo Next Step
Ask **Sales** to prepare the official customer quote.

### Sources
- **Steamships Client Onboarding FAQ**
- **Services Catalog — Steamships Trading Company**
""" + BASE_SYSTEM_PROMPT

STAFF_SYSTEM_PROMPT = """
You are answering in **STAFF mode**.
You may use internal SOPs, demo prices, price lists, and approval rules when they appear in Context.
For shipping quote/document questions, use this structure exactly:

### Quote Guidance
- Service: **20ft FCL, Lae → Port Moresby**
- Standard price: **PGK 4,500**

### Required Documents
**Client onboarding**
1. Registration form
2. KYC documents
3. Signed terms

**Container booking**
1. Commercial invoice
2. Packing list
3. Export permit, if applicable
4. Shipper and consignee details
5. Commodity, weight, volume, container type and quantity

### Odoo Next Step
Create the quotation in Odoo using the correct customer pricelist. If the discount is **above 10%**, request **manager approval** before sending.

### Sources
- **Steamships Standard Price List**
- **SOP-SHIP-004: Required Documents for Container Booking**
- **Client Onboarding Checklist**
""" + BASE_SYSTEM_PROMPT


def system_prompt_for(mode: str) -> str:
    """Pick the right system prompt for the requesting audience."""
    if (mode or "").lower() == "staff":
        return STAFF_SYSTEM_PROMPT
    return CLIENT_SYSTEM_PROMPT
```

- [ ] **Step 2: Smoke-check import**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -c "from app.rag.prompts import system_prompt_for; print(system_prompt_for('staff')[:80])"
```

Expected: prints `You are answering in **STAFF mode**.`.

---

### Task 6: Write `app/ocr/schemas.py` and stubs

**Files:**

- Create: `services/steamships-ai-api/app/ocr/schemas.py`
- Create: `services/steamships-ai-api/app/ocr/bill_of_lading.py`
- Create: `services/steamships-ai-api/app/ocr/invoice.py`

- [ ] **Step 1: Create `app/ocr/schemas.py`**

Create `services/steamships-ai-api/app/ocr/schemas.py`:

```python
"""Pydantic schemas for the OCR endpoints.

The shapes match the requirements document (sections 3, 10) so the existing
Odoo `steamships_document_ai` wizard continues to receive a predictable
response.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class BillOfLadingResponse(BaseModel):
    bl_number: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    vessel_name: Optional[str] = None
    voyage_number: Optional[str] = None
    container_numbers: List[str] = Field(default_factory=list)
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    cargo_description: Optional[str] = None
    weight: Optional[str] = None
    date: Optional[str] = None
    confidence: Dict[str, float] = Field(default_factory=dict)
    detected_document_type: str = "bill_of_lading"


class InvoiceResponse(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[str] = None
    currency: Optional[str] = None
    line_items: List[dict] = Field(default_factory=list)
    confidence: Dict[str, float] = Field(default_factory=dict)
    detected_document_type: str = "invoice"
    status: str = "not_implemented"
```

- [ ] **Step 2: Create the B/L stub `app/ocr/bill_of_lading.py`**

Create `services/steamships-ai-api/app/ocr/bill_of_lading.py`:

```python
"""Bill of Lading OCR — placeholder extraction.

The original regex + vision-AI logic lives in
``services/document_ai_api/main.py``. This stub returns the schema-correct
shape with all fields null so the Odoo wizard can call the new endpoint
without crashing. Replace the body with the real extractor once the
``document-ai`` service is merged in.
"""

from __future__ import annotations

from .schemas import BillOfLadingResponse


def extract_bill_of_lading(filename: str, content: bytes, mimetype: str | None) -> BillOfLadingResponse:
    """Return an empty-but-shape-correct B/L payload.

    TODO(merge-ocr): wire the existing extractor from
    ``services/document_ai_api/main.py`` here. For now we return nulls with
    zero confidence so downstream callers can render a clean "pending" UI.
    """
    return BillOfLadingResponse()
```

- [ ] **Step 3: Create the invoice stub `app/ocr/invoice.py`**

Create `services/steamships-ai-api/app/ocr/invoice.py`:

```python
"""Supplier-invoice OCR — placeholder.

Like ``bill_of_lading.py``, this is a stub that returns the schema with
``status="not_implemented"``. The real extractor will be merged in once the
OCR service consolidation lands.
"""

from __future__ import annotations

from .schemas import InvoiceResponse


def extract_invoice(filename: str, content: bytes, mimetype: str | None) -> InvoiceResponse:
    """Return a ``not_implemented`` invoice payload."""
    return InvoiceResponse()
```

- [ ] **Step 4: Smoke-check import**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -c "from app.ocr import bill_of_lading, invoice; from app.ocr.schemas import BillOfLadingResponse, InvoiceResponse; print('ok')"
```

Expected: prints `ok`.

---

### Task 7: Write `app/main.py` — FastAPI app + endpoints

**Files:**

- Create: `services/steamships-ai-api/app/main.py`
- Test: `services/steamships-ai-api/tests/test_health.py`
- Test: `services/steamships-ai-api/tests/test_auth.py`
- Test: `services/steamships-ai-api/tests/test_retrieve_shape.py`
- Test: `services/steamships-ai-api/tests/test_ocr_shape.py`

- [ ] **Step 1: Write `tests/test_health.py` first**

Create `services/steamships-ai-api/tests/test_health.py`:

```python
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
```

- [ ] **Step 2: Write `tests/test_auth.py` first**

Create `services/steamships-ai-api/tests/test_auth.py`:

```python
"""Auth-required tests for the protected POST endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client(monkeypatch: pytest.MonkeyPatch):
    """TestClient with AI_API_TOKEN forced to 'secret'."""
    monkeypatch.setenv("AI_API_TOKEN", "secret-token")
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
    # Stub the LLM call to avoid touching OpenAI.
    from app.main import retrieve as main_retrieve

    monkeypatch.setattr(
        main_retrieve,
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
```

- [ ] **Step 3: Write `tests/test_retrieve_shape.py` first**

Create `services/steamships-ai-api/tests/test_retrieve_shape.py`:

```python
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
```

- [ ] **Step 4: Write `tests/test_ocr_shape.py` first**

Create `services/steamships-ai-api/tests/test_ocr_shape.py`:

```python
"""Verify the OCR endpoints return the strict JSON shapes from the spec."""

from __future__ import annotations

from fastapi.testclient import TestClient


BL_REQUIRED_KEYS = {
    "bl_number",
    "shipper",
    "consignee",
    "notify_party",
    "vessel_name",
    "voyage_number",
    "container_numbers",
    "port_of_loading",
    "port_of_discharge",
    "cargo_description",
    "weight",
    "date",
    "confidence",
}


def _upload(client: TestClient, path: str) -> "requests.Response":  # type: ignore[name-defined]
    with open(path, "rb") as fh:
        return client.post(
            "/api/ocr/bill-of-lading",
            files={"file": ("sample.bin", fh, "application/octet-stream")},
        )


def test_bill_of_lading_returns_required_keys(
    client: TestClient, tmp_path
) -> None:
    fake = tmp_path / "bl.pdf"
    fake.write_bytes(b"%PDF-1.4\n%fake\n%%EOF")
    r = _upload(client, str(fake))
    assert r.status_code == 200, r.text
    body = r.json()
    assert BL_REQUIRED_KEYS.issubset(body.keys()), body
    # All fields are nullable in the stub.
    assert body["bl_number"] is None
    assert body["container_numbers"] == []
    assert body["confidence"] == {}


def test_invoice_returns_not_implemented_status(client: TestClient, tmp_path) -> None:
    fake = tmp_path / "inv.pdf"
    fake.write_bytes(b"%PDF-1.4\n%fake\n%%EOF")
    with open(fake, "rb") as fh:
        r = client.post(
            "/api/ocr/invoice",
            files={"file": ("inv.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "not_implemented"
```

- [ ] **Step 5: Run tests — expect import errors**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 6: Implement `app/main.py`**

Create `services/steamships-ai-api/app/main.py`:

```python
"""FastAPI entry point for the steamships-ai-api service.

Endpoints
---------
GET  /health                     - liveness, no auth
POST /api/retrieve               - RAG retrieve + LLM answer (auth required if AI_API_TOKEN set)
POST /api/ocr/bill-of-lading     - Bill of Lading OCR (auth required if AI_API_TOKEN set)
POST /api/ocr/invoice            - Invoice OCR (auth required if AI_API_TOKEN set)
POST /api/ingest/rebuild         - Rebuild the vector index (auth required if AI_API_TOKEN set)

Behaviour preserved from the legacy ``rag/`` service so the Odoo controller
keeps working without code changes (other than the new ``X-AI-Token`` header
and a different default hostname ``ai-api`` instead of ``rag-api``).
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from openai import OpenAI

from .config import Settings, get_settings
from .ocr.bill_of_lading import extract_bill_of_lading
from .ocr.invoice import extract_invoice
from .rag.ingest import (
    Chunk,
    build_chunks,
    embed_chunks,
    get_or_create_collection,
    upsert_chunks,
)
from .rag.manifest import Manifest
from .rag.prompts import system_prompt_for
from .rag.retrieve import MODE_CLIENT, MODE_STAFF, query_chunks
from .rag.schemas import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunk,
)
from .security import require_token

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Loading embedding model: %s", settings.embedding_model)
    app.state.settings = settings
    # Importing sentence_transformers lazily so test runs that don't touch
    # the embedding path don't have to download the model.
    from sentence_transformers import SentenceTransformer

    app.state.model = SentenceTransformer(settings.embedding_model)
    app.state.collection = get_or_create_collection(
        settings.chroma_path, settings.collection_name
    )
    app.state.manifest = Manifest.load(settings.manifest_path)
    logger.info(
        "RAG API ready (collection=%s, chunks=%d)",
        settings.collection_name,
        app.state.collection.count(),
    )
    yield


app = FastAPI(
    title="steamships-ai-api",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# /health (no auth)
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    """Return the service identity payload. Never requires a token."""
    return {"status": "ok", "service": "steamships-ai-api"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_odoo_next_step(answer: str, mode: str) -> str:
    """Keep demo quote answers on the agreed section contract."""
    if "### Quote Guidance" not in answer and "### Required Documents" not in answer:
        return answer
    answer = re.sub(r"### Next Steps?", "### Odoo Next Step", answer)
    if "### Odoo Next Step" in answer:
        return answer
    if mode == MODE_STAFF:
        block = (
            "### Odoo Next Step\n"
            "Create the quotation in Odoo using the correct customer pricelist. "
            "If the discount is **above 10%**, request **manager approval** before sending."
        )
    else:
        block = (
            "### Odoo Next Step\n"
            "Ask **Sales** to prepare the official customer quote."
        )
    if "### Sources" in answer:
        return answer.replace("### Sources", f"{block}\n\n### Sources", 1)
    return f"{answer}\n\n{block}"


def _synthesise_answer(
    settings: Settings,
    question: str,
    mode: str,
    context: str,
    chunks: List[RetrievedChunk],
) -> str:
    """Run the OpenAI-compatible chat completion.

    When no API key / base URL is configured we return a friendly, safe
    message instead of raising — this keeps /api/retrieve's contract intact
    during local dev when the user has not yet set GROQ_API_KEY.
    """
    if not settings.llm_api_key:
        return (
            "AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE "
            "or set OPENAI_API_KEY/GROQ_API_KEY for the AI API."
        )

    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"
    try:
        completion = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system_prompt_for(mode)},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        return "AI service is unavailable. Please try again shortly."

    raw = (completion.choices[0].message.content or "").strip()
    fence = re.match(r"^```(?:markdown|md|html|json)?\s*\n(.*)\n```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    raw = _ensure_odoo_next_step(raw, mode)

    source_names = list(dict.fromkeys(c.doc_name for c in chunks if c.doc_name))
    if source_names and "### Sources" not in raw:
        raw += "\n\n### Sources\n" + "\n".join(f"- **{n}**" for n in source_names[:5])
    return raw


# ---------------------------------------------------------------------------
# /api/retrieve
# ---------------------------------------------------------------------------
@app.post("/api/retrieve", response_model=RetrieveResponse)
def retrieve(
    req: RetrieveRequest,
    _token: None = Depends(require_token),
) -> RetrieveResponse:
    """RAG retrieve + LLM answer.

    Matches the shape consumed by ``custom_addons/steamships_ai/controllers/main.py``.
    """
    chunks = query_chunks(
        question=req.question,
        mode=req.mode,
        top_k=req.top_k,
        collection=app.state.collection,
        model=app.state.model,
    )
    context = "\n\n".join(
        f"Source: {c.doc_name}\nSection: {c.section}\nText:\n{c.text}" for c in chunks
    ) if chunks else ""

    settings = app.state.settings
    answer = _synthesise_answer(settings, req.question, req.mode, context, chunks)

    return RetrieveResponse(
        question=req.question,
        mode=req.mode,
        chunks=chunks,
        answer=answer,
    )


# ---------------------------------------------------------------------------
# OCR endpoints
# ---------------------------------------------------------------------------
@app.post("/api/ocr/bill-of-lading")
def ocr_bill_of_lading(
    file: UploadFile = File(...),
    _token: None = Depends(require_token),
):
    """Extract Bill of Lading fields from a PDF/PNG/JPG."""
    content = file.file.read()
    payload = extract_bill_of_lading(file.filename or "upload.bin", content, file.content_type)
    return payload.model_dump()


@app.post("/api/ocr/invoice")
def ocr_invoice(
    file: UploadFile = File(...),
    _token: None = Depends(require_token),
):
    """Extract supplier-invoice fields. Stub returns ``status=not_implemented``."""
    content = file.file.read()
    payload = extract_invoice(file.filename or "upload.bin", content, file.content_type)
    return payload.model_dump()


# ---------------------------------------------------------------------------
# /api/ingest/rebuild
# ---------------------------------------------------------------------------
@app.post("/api/ingest/rebuild", response_model=IngestResponse)
def ingest_rebuild(
    req: IngestRequest | None = None,
    _token: None = Depends(require_token),
) -> IngestResponse:
    """Rebuild the vector index from the configured docs path."""
    req = req or IngestRequest()
    settings: Settings = app.state.settings
    docs_path = req.docs_path or settings.docs_path
    chunk_size = req.chunk_size or settings.chunk_size
    chunk_overlap = req.chunk_overlap or settings.chunk_overlap

    try:
        chunks = build_chunks(docs_path, app.state.manifest, chunk_size, chunk_overlap)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    documents_processed = len({c.filename for c in chunks})
    embed_chunks(chunks, app.state.model)
    inserted = upsert_chunks(chunks, app.state.collection)

    return IngestResponse(
        documents_processed=documents_processed,
        chunks_inserted=inserted,
        collection_name=settings.collection_name,
    )
```

- [ ] **Step 7: Run tests — expect PASS**

Run:
```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/ -v
```

Expected: all tests pass.

Notes:
- `test_auth.py` may need a tiny adjustment if FastAPI's TestClient does not start the lifespan — we wrap with `with TestClient(app) as c` which starts lifespan; embedding download is heavy. If the test environment lacks network for the embedding model, monkeypatch `app.state.model` in the `test_retrieve_with_correct_token_is_accepted_shape` test. The existing `test_retrieve_no_key_returns_clean_shape` already avoids the LLM path so it should pass without network.

If the embedding model download blocks CI, also add a top-level `conftest.py` patch:

```python
# Add to services/steamships-ai-api/tests/conftest.py at the bottom:
import pytest


@pytest.fixture(autouse=True)
def _stub_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid downloading the embedding model during the test session."""
    import sys
    import types

    if "sentence_transformers" in sys.modules:
        return
    fake = types.ModuleType("sentence_transformers")

    class _FakeModel:
        def encode(self, *args, **kwargs):
            import numpy as np
            arr = np.zeros((len(args[0]) if args else 1, 4), dtype="float32")
            return arr

    fake.SentenceTransformer = lambda *_a, **_k: _FakeModel()
    sys.modules["sentence_transformers"] = fake
```

Add this snippet as a separate edit step:

```bash
# Append the fixture to conftest.py (the file we created in Task 1).
```

If the existing conftest needs this, edit `services/steamships-ai-api/tests/conftest.py` to add the fixture above.

---

### Task 8: Add the `requirements.txt` and a `Dockerfile`

**Files:**

- Create: `services/steamships-ai-api/requirements.txt`
- Create: `services/steamships-ai-api/Dockerfile`

- [ ] **Step 1: Write `requirements.txt`**

Create `services/steamships-ai-api/requirements.txt`:

```text
# FastAPI + uvicorn
fastapi==0.115.0
uvicorn[standard]==0.32.0

# Forms / uploads
python-multipart>=0.0.9

# Pydantic v2
pydantic==2.9.2
pydantic-settings>=2.5,<3

# Odoo side calls us with `requests`; we use stdlib for HTTP, but keep
# requests available for any future outbound calls (mirrors Odoo side).
requests>=2.32

# RAG
chromadb==0.5.5
sentence-transformers==3.1.1
openai==1.54.0

# OCR — only what we use today (PyMuPDF for PDF raster; PIL for images).
pymupdf>=1.24,<2.0
pillow>=10.0

# Tests
pytest>=8.0
httpx<0.28
```

- [ ] **Step 2: Write the `Dockerfile`**

Create `services/steamships-ai-api/Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages:
#  - build-essential / gcc / python3-dev: Chroma's onnxruntime + hnswlib
#    native extensions.
#  - poppler-utils: PDF rendering (OCR path).
#  - libgl1 / libglib2.0-0: PIL wheels that link against libGL.
#  - tesseract-ocr: kept in case we fall back to local OCR during tests.
#  - curl: healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        python3-dev \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Pre-download the embedding model so the first request is fast.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app /app/app

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-9000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
```

- [ ] **Step 3: Confirm the file tree**

Run:
```bash
find services/steamships-ai-api -type f | sort
```

Expected (subset):
```
services/steamships-ai-api/Dockerfile
services/steamships-ai-api/requirements.txt
services/steamships-ai-api/.env.example
services/steamships-ai-api/app/__init__.py
services/steamships-ai-api/app/config.py
services/steamships-ai-api/app/main.py
services/steamships-ai-api/app/security.py
services/steamships-ai-api/app/rag/__init__.py
services/steamships-ai-api/app/rag/ingest.py
services/steamships-ai-api/app/rag/manifest.py
services/steamships-ai-api/app/rag/prompts.py
services/steamships-ai-api/app/rag/retrieve.py
services/steamships-ai-api/app/rag/schemas.py
services/steamships-ai-api/app/ocr/__init__.py
services/steamships-ai-api/app/ocr/bill_of_lading.py
services/steamships-ai-api/app/ocr/invoice.py
services/steamships-ai-api/app/ocr/schemas.py
services/steamships-ai-api/tests/__init__.py
services/steamships-ai-api/tests/conftest.py
services/steamships-ai-api/tests/test_auth.py
services/steamships-ai-api/tests/test_config.py
services/steamships-ai-api/tests/test_health.py
services/steamships-ai-api/tests/test_ocr_shape.py
services/steamships-ai-api/tests/test_retrieve_shape.py
services/steamships-ai-api/tests/test_security.py
```

---

### Task 9: Add README for the service

**Files:**

- Create: `services/steamships-ai-api/README.md`

- [ ] **Step 1: Write the README**

Create `services/steamships-ai-api/README.md`:

```markdown
# steamships-ai-api

Stand-alone FastAPI service that powers the Steamships Odoo chatbot and the
OCR review flow. Split out of the legacy `rag/` folder so it can be deployed
independently on Railway / Render / a VPS, while keeping local
`docker compose` happy.

## What this service does

- **RAG retrieve** — `POST /api/retrieve`. Embed a question, query Chroma,
  generate an answer with the configured LLM (Groq by default).
- **Bill of Lading OCR** — `POST /api/ocr/bill-of-lading`. Stub today; will
  be merged with `services/document_ai_api` in a follow-up.
- **Invoice OCR** — `POST /api/ocr/invoice`. Stub today; returns
  `status: not_implemented`.
- **Index rebuild** — `POST /api/ingest/rebuild`. Re-build the Chroma
  collection from `DOCS_PATH`.
- **Health** — `GET /health`. No auth, returns `{status, service}`.

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET    | `/health` | none | Liveness |
| POST   | `/api/retrieve` | `X-AI-Token` (if set) | RAG + LLM answer |
| POST   | `/api/ocr/bill-of-lading` | `X-AI-Token` (if set) | B/L extraction |
| POST   | `/api/ocr/invoice` | `X-AI-Token` (if set) | Invoice extraction |
| POST   | `/api/ingest/rebuild` | `X-AI-Token` (if set) | Rebuild vector index |

Auth is enforced when `AI_API_TOKEN` is non-empty. Send `X-AI-Token: <token>`
or `Authorization: Bearer <token>`. Missing/wrong token → 401.

## Env vars

See `.env.example` for the full list. The Odoo side also reads
`RAG_API_BASE`, `OCR_API_BASE`, `AI_API_TOKEN`, `RAG_RETRIEVE_TIMEOUT`.

## Local Docker build

```bash
cd services/steamships-ai-api
docker build -t steamships-ai-api .
docker run --env-file .env -p 9000:9000 steamships-ai-api
curl http://localhost:9000/health
```

## Local docker compose (from repo root)

```bash
cp .env.example .env  # edit AI_API_TOKEN, GROQ_API_KEY, etc.
docker compose build ai-api
docker compose up -d ai-api
curl http://localhost:9000/health
```

## Railway deploy

1. New Project → Deploy from GitHub repo.
2. **Root Directory:** `services/steamships-ai-api`.
3. Railway auto-detects the `Dockerfile`. Override the start command only if
   you need a non-default port.
4. Add env vars (see `.env.example`). **Do not** paste the same token you
   use locally — generate a fresh one for prod.
5. If you keep Chroma on Railway, add a Volume mounted at `/data/chroma`.

## Render deploy

1. New Web Service → Docker.
2. **Root Directory:** `services/steamships-ai-api`.
3. **Dockerfile Path:** `Dockerfile`.
4. Add the same env vars as Railway.
5. For persistent Chroma, attach a Disk mounted at `/data/chroma`.

## Migrating from the legacy `rag/` service

The `rag/` folder in the repo root is deprecated. See
[`legacy/README.md`](../../legacy/README.md) for the redirect.

## Tests

```bash
cd services/steamships-ai-api
pip install -r requirements.txt
PYTHONPATH=. python -m pytest tests/ -v
```
```

---

### Task 10: Update the Odoo `steamships_ai` controller

**Files:**

- Create: `custom_addons/steamships_ai/services/__init__.py`
- Create: `custom_addons/steamships_ai/services/ai_api_client.py`
- Modify: `custom_addons/steamships_ai/controllers/main.py`
- Modify: `custom_addons/steamships_ai/__manifest__.py`

- [ ] **Step 1: Create the package + helper `ai_api_client.py`**

Create `custom_addons/steamships_ai/services/__init__.py`:

```python
# Empty marker — see ai_api_client.py.
```

Create `custom_addons/steamships_ai/services/ai_api_client.py`:

```python
"""Thin client for the stand-alone steamships-ai-api service.

Centralises:
- Base URL resolution (``RAG_API_BASE`` / ``OCR_API_BASE``).
- Optional ``X-AI-Token`` header (when ``AI_API_TOKEN`` is set).
- Multipart upload for OCR endpoints.
- A ``user-friendly error`` message when the AI service is unreachable.

The existing controllers already wrap this client with their own JSON-RPC
shape (``ok`` / ``status`` keys). Keep the wrapper behaviour unchanged so
the chatbot widget keeps working.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

_logger = logging.getLogger(__name__)


DEFAULT_RAG_BASE = "http://ai-api:9000"
DEFAULT_OCR_BASE = "http://ai-api:9000"
DEFAULT_TIMEOUT = 15.0


class AIServiceError(Exception):
    """Raised when the AI service cannot be reached or returns an error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class AIAPIClient:
    """Reusable HTTP client for both RAG and OCR endpoints.

    Construct once per request (the cost is negligible — just reading env
    vars) and call :meth:`retrieve` / :meth:`ocr_bill_of_lading` /
    :meth:`ocr_invoice`. Methods raise :class:`AIServiceError` on any
    non-success outcome.
    """

    def __init__(
        self,
        rag_base: Optional[str] = None,
        ocr_base: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.rag_base = (rag_base or os.environ.get("RAG_API_BASE") or DEFAULT_RAG_BASE).rstrip("/")
        self.ocr_base = (ocr_base or os.environ.get("OCR_API_BASE") or DEFAULT_OCR_BASE).rstrip("/")
        self.token = (token if token is not None else os.environ.get("AI_API_TOKEN") or "").strip()
        self.timeout = float(os.environ.get("RAG_RETRIEVE_TIMEOUT", timeout))

    # ------------------------------------------------------------------
    # Headers / helpers
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        headers: dict[str, str] = {}
        if self.token:
            headers["X-AI-Token"] = self.token
        return headers

    def _post_json(self, url: str, payload: dict) -> dict:
        """POST JSON, raise AIServiceError on failure."""
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
        except requests.Timeout as exc:
            _logger.exception("AI API timeout after %.1fs (%s)", self.timeout, url)
            raise AIServiceError(
                "The AI service is taking too long to reply. Please try again in a moment."
            ) from exc
        except requests.ConnectionError as exc:
            _logger.exception("AI API connection error: %s", url)
            raise AIServiceError(
                "AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE."
            ) from exc
        except requests.RequestException as exc:
            _logger.exception("AI API request error: %s", exc)
            raise AIServiceError(
                "The AI service could not be reached. Please try again later."
            ) from exc
        if not resp.ok:
            _logger.error("AI API HTTP %s: %s", resp.status_code, resp.text[:300])
            raise AIServiceError(
                f"AI service returned HTTP {resp.status_code}.", status_code=resp.status_code
            )
        try:
            return resp.json()
        except ValueError as exc:
            _logger.exception("AI API returned non-JSON: %r", resp.text[:300])
            raise AIServiceError("AI service returned an unexpected response.") from exc

    def _post_multipart(self, url: str, filename: str, content: bytes, mimetype: str) -> dict:
        try:
            resp = requests.post(
                url,
                files={"file": (filename, content, mimetype or "application/octet-stream")},
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            _logger.exception("AI API OCR timeout: %s", url)
            raise AIServiceError("OCR service timeout. Please try again.") from exc
        except requests.ConnectionError as exc:
            _logger.exception("AI API OCR connection error: %s", url)
            raise AIServiceError("AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE.") from exc
        except requests.RequestException as exc:
            _logger.exception("AI API OCR request error: %s", exc)
            raise AIServiceError("OCR service could not be reached.") from exc
        if not resp.ok:
            _logger.error("AI API OCR HTTP %s: %s", resp.status_code, resp.text[:300])
            raise AIServiceError(
                f"OCR service returned HTTP {resp.status_code}.", status_code=resp.status_code
            )
        try:
            return resp.json()
        except ValueError as exc:
            _logger.exception("AI API OCR returned non-JSON: %r", resp.text[:300])
            raise AIServiceError("OCR service returned an unexpected response.") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def retrieve(self, question: str, mode: str = "staff", top_k: int = 5) -> dict:
        """Call ``POST /api/retrieve`` and return the parsed JSON."""
        payload = {"question": question, "mode": mode, "top_k": top_k}
        url = f"{self.rag_base}/api/retrieve"
        _logger.info("POST %s payload=%s", url, {"question": question, "mode": mode, "top_k": top_k})
        return self._post_json(url, payload)

    def ocr_bill_of_lading(self, filename: str, content: bytes, mimetype: str) -> dict:
        """Call ``POST /api/ocr/bill-of-lading`` and return the parsed JSON."""
        url = f"{self.ocr_base}/api/ocr/bill-of-lading"
        return self._post_multipart(url, filename, content, mimetype)

    def ocr_invoice(self, filename: str, content: bytes, mimetype: str) -> dict:
        """Call ``POST /api/ocr/invoice`` and return the parsed JSON."""
        url = f"{self.ocr_base}/api/ocr/invoice"
        return self._post_multipart(url, filename, content, mimetype)

    def health(self) -> Any:
        """Call ``GET /health`` — used by smoke checks only."""
        url = f"{self.rag_base}/health"
        resp = requests.get(url, headers=self._headers(), timeout=5.0)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 2: Replace the controller with the new client**

Edit `custom_addons/steamships_ai/controllers/main.py`:

- Replace the top-of-file constants block with:

```python
import logging

from odoo import _, http

from ..services.ai_api_client import AIAPIClient, AIServiceError

_logger = logging.getLogger(__name__)

VALID_MODES = {"staff", "client"}
```

- Replace the entire `SteamshipsAIController` class body. Keep the route
  decorators and signatures unchanged. Below is the full replacement
  class:

```python
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
```

- [ ] **Step 3: Update the manifest**

Edit `custom_addons/steamships_ai/__manifest__.py`:

- Update `version` to `"19.0.1.1.0"`.
- Update the `description` text to mention `AI_API_BASE` / `AI_API_TOKEN`.
- No new `data`/`assets` entries are required (the controller still
  re-uses the existing template).

- [ ] **Step 4: Compile-check**

Run:
```bash
python -c "import ast; ast.parse(open('custom_addons/steamships_ai/controllers/main.py').read()); ast.parse(open('custom_addons/steamships_ai/services/ai_api_client.py').read()); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Upgrade the module**

After Docker compose is up (Task 13):
```bash
./scripts/update-module.sh steamships_ai
```

Expected: Odoo upgrades the module without errors.

---

### Task 11: Update the OCR wizard to use `OCR_API_BASE` + token

**Files:**

- Modify: `custom_addons/steamships_document_ai/wizards/document_upload_wizard.py`

- [ ] **Step 1: Patch the env lookup**

Edit `custom_addons/steamships_document_ai/wizards/document_upload_wizard.py`:

- Replace `DEFAULT_OCR_URL = "http://document-ai:9100"` with:

```python
# Default to the unified AI API on port 9000; the legacy
# ``document-ai:9100`` hostname still works for the old stand-alone OCR
# container until the migration finishes.
DEFAULT_OCR_URL = "http://ai-api:9000"
```

- Inside `_ocr_base_url`, also read `OCR_API_TOKEN` (if present) and
  attach it to the multipart upload:

  Replace the method:

```python
def _ocr_base_url(self):
    return os.environ.get("OCR_API_BASE", DEFAULT_OCR_URL).rstrip("/") + "/"
```

  With:

```python
def _ocr_base_url(self):
    return os.environ.get("OCR_API_BASE", DEFAULT_OCR_URL).rstrip("/") + "/"

def _ocr_token(self):
    return (os.environ.get("AI_API_TOKEN") or os.environ.get("OCR_API_TOKEN") or "").strip()
```

- Update `_post_file` so the token is sent when set. Find this block:

```python
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
```

  Replace with:

```python
        if self._ocr_token():
            headers["X-AI-Token"] = self._ocr_token()
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
```

  And update the 401 error message to:

```python
            raise UserError(
                _(
                    "OCR service returned HTTP 401. Please check the AI_API_TOKEN env "
                    "value shared between Odoo and the AI API."
                )
            ) from exc
```

  (Only replace the `HTTPError` branch when `exc.code == 401`. For other
  HTTP errors keep the existing message.)

- [ ] **Step 2: Compile-check**

Run:
```bash
python -c "import ast; ast.parse(open('custom_addons/steamships_document_ai/wizards/document_upload_wizard.py').read()); print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Upgrade the module after Docker is up**

```bash
./scripts/update-module.sh steamships_document_ai
```

Expected: Odoo upgrades without errors.

---

### Task 12: Update `.env.example`

**Files:**

- Modify: `.env.example`

- [ ] **Step 1: Add the AI API block**

Append to `.env.example` (do **not** remove existing Gmail / OCA SHA lines):

```bash
# === AI API (steamships-ai-api) ===
AI_API_PORT=9000
AI_API_TOKEN=change-me-local-dev
RAG_API_BASE=http://ai-api:9000
OCR_API_BASE=http://ai-api:9000
RAG_RETRIEVE_TIMEOUT=20

# === RAG ===
CHROMA_PATH=/data/chroma
COLLECTION_NAME=steamships_rag
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
DOCS_PATH=/docs/mock/rag_documents
MANIFEST_PATH=/docs/mock/rag_documents/MANIFEST_ingestion_metadata.json
CHUNK_SIZE=800
CHUNK_OVERLAP=100
TOP_K=5

# === LLM ===
GROQ_API_KEY=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

- [ ] **Step 2: Verify the file**

Run:
```bash
grep -c '^AI_API' .env.example
grep -c '^RAG_API_BASE' .env.example
```

Expected: both return `>= 1`.

---

### Task 13: Update `docker-compose.yml`

**Files:**

- Modify: `docker-compose.yml`

- [ ] **Step 1: Rename the service**

Replace the `rag-api:` block with:

```yaml
  ai-api:
    # Day 7 split — stand-alone FastAPI service that powers both RAG and OCR.
    # Lives in services/steamships-ai-api/. The legacy `rag-api` hostname
    # still resolves via the network alias below so any older config keeps
    # working until fully migrated.
    build:
      context: ./services/steamships-ai-api
      dockerfile: Dockerfile
    container_name: steamships_ai_api
    command: ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${AI_API_PORT:-9000} --reload"]
    env_file: .env
    environment:
      PORT: ${AI_API_PORT:-9000}
      AI_API_TOKEN: ${AI_API_TOKEN}
      CHROMA_PATH: /data/chroma
      COLLECTION_NAME: steamships_rag
      DOCS_PATH: /docs/mock/rag_documents
      MANIFEST_PATH: /docs/mock/rag_documents/MANIFEST_ingestion_metadata.json
      CHUNK_SIZE: "800"
      CHUNK_OVERLAP: "100"
      TOP_K: "5"
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-sentence-transformers/all-MiniLM-L6-v2}
      GROQ_API_KEY: ${GROQ_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-${GROQ_API_KEY}}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.groq.com/openai/v1}
      OPENAI_MODEL: ${OPENAI_MODEL:-llama-3.3-70b-versatile}
    volumes:
      - ./chroma_data:/data/chroma
      - ./mock_data:/docs/mock:ro
      - ./services/steamships-ai-api/app:/app/app
    ports:
      - "${AI_API_PORT:-9000}:9000"
    networks:
      default:
        aliases:
          - ai-api
          - rag-api     # legacy alias for backward compatibility
    restart: unless-stopped
```

- [ ] **Step 2: Wire AI_API_TOKEN into the Odoo service**

In the `odoo:` service, add the following env vars inside the `environment:` map (between the `GROQ_API_KEY:` line and the `volumes:` block):

```yaml
      # === Day 7 split — call the unified AI API ===
      RAG_API_BASE: ${RAG_API_BASE:-http://ai-api:9000}
      OCR_API_BASE: ${OCR_API_BASE:-http://ai-api:9000}
      AI_API_TOKEN: ${AI_API_TOKEN}
      RAG_RETRIEVE_TIMEOUT: ${RAG_RETRIEVE_TIMEOUT:-20}
```

- [ ] **Step 3: Lint the YAML**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))" && echo ok
```

Expected: prints `ok`.

- [ ] **Step 4: Stop the old container + bring the new one up**

Run:
```bash
docker compose down
docker compose build ai-api
docker compose up -d db ai-api odoo
```

Expected: containers come up healthy.

- [ ] **Step 5: Smoke /health**

Run:
```bash
sleep 5
curl -fsS http://localhost:9000/health
```

Expected: `{"status":"ok","service":"steamships-ai-api"}`.

- [ ] **Step 6: Re-upsert the legacy chroma collection (so old chunks survive)**

Run:
```bash
curl -fsS -X POST http://localhost:9000/api/ingest/rebuild \
    -H "X-AI-Token: change-me-local-dev" \
    -H "Content-Type: application/json" \
    -d '{}'
```

Expected: `{"documents_processed": <N>, "chunks_inserted": <N>, "collection_name": "steamships_rag"}` where `N` matches `mock_data/rag_documents/*.md` count.

- [ ] **Step 7: Hit `/ask-ai`**

Open `http://localhost:8069/web/login`, log in, then visit
`http://localhost:8069/ask-ai`. Ask a question. Expect a Markdown answer
plus a sources list. If `GROQ_API_KEY` is unset the answer will be the
"AI service is unavailable..." message — that is correct behaviour.

---

### Task 14: Update the root `README.md`

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Replace the existing README content**

Write the new root `README.md`:

```markdown
# Odoo 19.0 Dev Environment

Local Docker-based Odoo 19.0 Community + PostgreSQL 16, with OCA modules and a
custom module scaffold. The RAG and OCR logic lives in a separate FastAPI
service (`services/steamships-ai-api/`) so it can be deployed independently
on Railway / Render / a VPS, while Odoo stays on OEC.

## Architecture

```
Odoo container (steamships_ai + steamships_document_ai)
        │  HTTP (RAG_API_BASE, OCR_API_BASE, X-AI-Token)
        ▼
steamships-ai-api container (FastAPI on :9000)
        │              │
        ▼              ▼
Chroma DB         LLM provider
(/data/chroma)    (Groq / OpenAI)
```

In production, Odoo and the AI API are deployed separately:

- **Odoo** → OEC (or any Odoo 19 host).
- **steamships-ai-api** → Railway / Render / VPS / Fly.io.
- The AI API and Odoo share an `AI_API_TOKEN` value via env.

## Quickstart (local docker compose)

```bash
cp .env.example .env
docker compose build
docker compose up -d db
bash scripts/init-db.sh
docker compose up -d ai-api odoo
./scripts/update-module.sh steamships_ai
```

Then open <http://localhost:8069>. The chatbot widget is at
`http://localhost:8069/ask-ai` (log in first).

## AI API

See [`services/steamships-ai-api/README.md`](services/steamships-ai-api/README.md)
for the service README.

Smoke checks:

```bash
# Health
curl http://localhost:9000/health

# Retrieve (with token from .env)
TOKEN=change-me-local-dev
curl -X POST http://localhost:9000/api/retrieve \
  -H "Content-Type: application/json" \
  -H "X-AI-Token: $TOKEN" \
  -d '{"question":"A client wants to ship a 20ft container from Lae to Port Moresby. What price do I quote?","mode":"staff"}'

# OCR
curl -X POST http://localhost:9000/api/ocr/bill-of-lading \
  -H "X-AI-Token: $TOKEN" \
  -F "file=@some-sample.pdf"
```

## Deploy notes

### Odoo (OEC)

Set the following env vars on the Odoo app:

```
RAG_API_BASE=https://<your-ai-api-domain>
OCR_API_BASE=https://<your-ai-api-domain>
AI_API_TOKEN=<same-token-as-ai-api>
RAG_RETRIEVE_TIMEOUT=20
```

### steamships-ai-api (Railway / Render / VPS)

Set:

```
AI_API_TOKEN=<same-token-as-odoo>
OPENAI_API_KEY=...        # or GROQ_API_KEY
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
CHROMA_PATH=/data/chroma  # mount a volume here
COLLECTION_NAME=steamships_rag
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

See the [service README](services/steamships-ai-api/README.md) for
Railway / Render specifics.

## Upgrade a custom module

```bash
./scripts/update-module.sh <module_name>
```

## Reset

```bash
bash scripts/reset.sh --confirm-destructive
bash scripts/init-db.sh
docker compose up -d odoo
```
```

- [ ] **Step 2: Confirm the file**

Run:
```bash
head -20 README.md
```

Expected: shows the new "Architecture" section.

---

### Task 15: Move legacy `rag/` to `legacy/rag/` and update `.gitignore`

**Files:**

- Create: `legacy/README.md`
- Move: `rag/` → `legacy/rag/`

- [ ] **Step 1: Move the legacy folder**

```bash
mkdir -p legacy
git mv rag legacy/rag
```

- [ ] **Step 2: Write `legacy/README.md`**

```markdown
# Legacy code

This directory contains code that has been superseded by the
`steamships-ai-api` FastAPI service (`services/steamships-ai-api/`).

- `legacy/rag/` — the old Day-3 RAG FastAPI service that ran on port 9000.
  Kept temporarily for reference and rollback. Will be removed once the
  new service proves stable in production.
- `services/document_ai_api/` — the old Day-5 OCR FastAPI service that ran
  on port 9100. Still used by the `steamships_document_ai` wizard as a
  fallback while the OCR endpoints in `steamships-ai-api` are stubs.

When you no longer need the legacy RAG service, delete `legacy/rag/`.
```

- [ ] **Step 3: Update `.gitignore`**

Append to `.gitignore`:

```
# Day 7 split — steamships-ai-api ignores
uploads/
*.pdf
*.png
*.jpg
*.jpeg
```

Also remove the now-obsolete `chroma_data/` line if it duplicates the
top-level block (it does — the existing one is fine).

- [ ] **Step 4: Confirm the move**

Run:
```bash
ls legacy/rag/
git status --short | head -20
```

Expected: `legacy/rag/` exists; `git status` shows the rename.

---

### Task 16: Update the OCR `docker-compose.override.document-ai.yml`

The current override file expects a service named `document-ai`. We are
**not** removing the legacy OCR service in this plan; just verify the
override still works in tandem with the new `ai-api` service.

**Files:**

- Read: `docker-compose.override.document-ai.yml`

- [ ] **Step 1: Verify the override still loads**

Run:
```bash
docker compose -f docker-compose.yml -f docker-compose.override.document-ai.yml config --services
```

Expected output includes `db`, `odoo`, `ai-api`, `document-ai`.

- [ ] **Step 2: If the override references `ai-api` env vars**

No change needed — the override only adds `document-ai` env vars. Leave
as-is.

---

### Task 17: Local verification

**No file changes — only verification.**

- [ ] **Step 1: Run the AI API test suite**

```bash
cd services/steamships-ai-api
PYTHONPATH=. python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Build the AI API image**

```bash
cd ../..
docker compose build ai-api
```

Expected: build completes.

- [ ] **Step 3: Bring up the stack**

```bash
docker compose down
docker compose up -d db
bash scripts/init-db.sh
docker compose up -d ai-api odoo
./scripts/update-module.sh steamships_ai
./scripts/update-module.sh steamships_document_ai
```

Expected: each command exits 0.

- [ ] **Step 4: Hit `/health`**

```bash
curl -fsS http://localhost:9000/health
```

Expected: `{"status":"ok","service":"steamships-ai-api"}`.

- [ ] **Step 5: Hit `/ask-ai` in Odoo**

Open <http://localhost:8069/ask-ai>. Log in. Send any question.
Expected:
- Without `GROQ_API_KEY` in `.env`: chat shows the friendly
  "AI service is unavailable. Please check RAG_API_BASE/OCR_API_BASE."
  message.
- With `GROQ_API_KEY` set: chat shows a Markdown answer (with `### Sources`).

- [ ] **Step 6: Hit `/api/retrieve` directly**

```bash
TOKEN=change-me-local-dev
curl -fsS -X POST http://localhost:9000/api/retrieve \
  -H "Content-Type: application/json" \
  -H "X-AI-Token: $TOKEN" \
  -d '{"question":"What is the price for a 20ft container Lae to POM?","mode":"staff"}'
```

Expected: JSON with `answer`, `sources`, `chunks`. (No 500, no stack trace.)

- [ ] **Step 7: Hit `/api/ocr/bill-of-lading`**

```bash
echo "fake pdf" > /tmp/bl.pdf
curl -fsS -X POST http://localhost:9000/api/ocr/bill-of-lading \
  -H "X-AI-Token: $TOKEN" \
  -F "file=@/tmp/bl.pdf"
```

Expected: strict JSON with all required keys (`bl_number`, `shipper`, ...).

- [ ] **Step 8: Verify backward-compatible hostname**

From inside the `odoo` container, `http://rag-api:9000/health` must still
answer (legacy alias):

```bash
docker compose exec odoo curl -fsS http://rag-api:9000/health
```

Expected: same JSON as `/health`.

---

### Task 18: Final deliverables

**No code changes — only output to the user.**

- [ ] **Step 1: Build the change summary**

```bash
git status --short
git diff --stat HEAD~0
```

- [ ] **Step 2: Write the deliverable summary**

Report back to the user with:

1. Files changed (new + modified).
2. New architecture (1 paragraph + diagram).
3. How to run local (the exact command sequence from task 17).
4. How to deploy the AI API separately (link to
   `services/steamships-ai-api/README.md`, mention Railway + Render).
5. Env vars to set on OEC (`RAG_API_BASE`, `OCR_API_BASE`,
   `AI_API_TOKEN`, `RAG_RETRIEVE_TIMEOUT`).
6. Known limitations:
   - OCR endpoints are stubs returning `null` / `status: not_implemented`.
     The real Tesseract + vision-AI logic still lives in
     `services/document_ai_api/` until the merge.
   - The `legacy/rag/` folder is kept for rollback.
   - Chroma persistence depends on the host mounting
     `./chroma_data:/data/chroma`. On Railway/Render add a Volume / Disk.
7. Exact commands used to test (from tasks 17.4 / 17.6 / 17.7).

- [ ] **Step 3: Do NOT push or open a PR**

The user instructions say "Không push nếu chưa pass test local." Wait for
explicit user confirmation before pushing.

---

## Self-review checklist

After implementation, the implementing engineer should verify:

- [ ] `services/steamships-ai-api/tests/` all pass.
- [ ] `docker compose build ai-api` succeeds.
- [ ] `docker compose up -d ai-api odoo` boots clean.
- [ ] `/health` returns the required payload.
- [ ] `/ask-ai` does not crash even when `GROQ_API_KEY` is unset.
- [ ] `/api/retrieve` returns the old response shape `{answer, sources, chunks}`.
- [ ] `/api/ocr/bill-of-lading` returns the required strict JSON shape.
- [ ] Odoo container can still resolve `rag-api` (legacy alias).
- [ ] No real secrets in any committed file.
- [ ] `legacy/rag/` is preserved.
- [ ] `.gitignore` includes `uploads/`, `*.pdf`, `*.png`, `*.jpg`, `*.jpeg`.