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