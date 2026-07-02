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

The AI API and Odoo are deployed as two independent services. They only
talk to each other over HTTP, sharing a single `AI_API_TOKEN`.

### 1. steamships-ai-api (Railway / Render / Fly.io / VPS)

**Railway**

1. New Project → Deploy from GitHub repo.
2. **Root Directory:** `services/steamships-ai-api`.
3. **Dockerfile Path:** `Dockerfile` (auto-detected).
4. Env vars:
   ```
   AI_API_TOKEN=<prod-token>             # generate a long random string
   GROQ_API_KEY=<your-groq-key>
   OPENAI_API_KEY=                       # leave empty; GROQ_API_KEY is used
   OPENAI_BASE_URL=https://api.groq.com/openai/v1
   OPENAI_MODEL=llama-3.3-70b-versatile
   CHROMA_PATH=/data/chroma
   COLLECTION_NAME=steamships_rag
   DOCS_PATH=/app/mock_data/rag_documents
   MANIFEST_PATH=/app/mock_data/rag_documents/MANIFEST_ingestion_metadata.json
   EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   PRELOAD_EMBEDDING_MODEL=false         # keep false to avoid Railway build OOM
   ```
5. Add a Volume mounted at `/data/chroma` (Chroma persistence).
6. After first deploy, hit the rebuild endpoint once to seed the index:
   ```bash
   curl -X POST https://<ai-api-domain>/api/ingest/rebuild \
     -H "X-AI-Token: <prod-token>" \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

**Render** is the same — Docker Web Service, Root Directory =
`services/steamships-ai-api`, attach a Disk at `/data/chroma`.

**VPS** is the same Dockerfile with `docker run -p 9000:9000
--env-file .env -v $PWD/chroma_data:/data/chroma steamships-ai-api`.

### 2. Odoo (OEC / any Odoo 19 host)

Set these env vars on the Odoo app (or via `docker compose`):

```
RAG_API_BASE=https://<ai-api-domain>
OCR_API_BASE=https://<ai-api-domain>
AI_API_TOKEN=<same-prod-token-as-above>
RAG_RETRIEVE_TIMEOUT=20
```

The Odoo addons (`steamships_ai`, `steamships_document_ai`) read these at
request time. No code change is needed when moving from local dev to OEC —
just update the env values.

### Smoke-test the deployed stack

```bash
# 1) AI API health (no auth)
curl https://<ai-api-domain>/health

# 2) RAG retrieve
curl -X POST https://<ai-api-domain>/api/retrieve \
  -H "Content-Type: application/json" \
  -H "X-AI-Token: $AI_API_TOKEN" \
  -d '{"question":"A client wants to ship a 20ft container from Lae to Port Moresby. What price do I quote?","mode":"staff"}'

# 3) Bill of Lading OCR
curl -X POST https://<ai-api-domain>/api/ocr/bill-of-lading \
  -H "X-AI-Token: $AI_API_TOKEN" \
  -F "file=@sample-bl.pdf"

# 4) Odoo chatbot widget
# Open https://<odoo-domain>/ask-ai and ask the same shipping question.
# The widget calls RAG_API_BASE on the Odoo backend, which then proxies
# to the AI API.
```

See the [service README](services/steamships-ai-api/README.md) for
endpoint reference and troubleshooting.

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