# steamships-ai-api

Stand-alone FastAPI service that powers the Steamships Odoo chatbot and the
OCR review flow. Split out of the legacy `rag/` folder so it can be deployed
independently on Railway / Render / a VPS, while keeping local
`docker compose` happy.

## What this service does

- **RAG retrieve** — `POST /api/retrieve`. Embed a question, query Chroma,
  generate an answer with the configured LLM (Groq by default).
- **Bill of Lading OCR** — `POST /api/ocr/bill-of-lading`. Runs the
  Tesseract + regex pipeline (merged from the legacy
  `services/document_ai_api/`). Returns the unified B/L schema at the top
  level plus the legacy nested `fields` object so the existing Odoo
  wizard keeps working.
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