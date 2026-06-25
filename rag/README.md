# Steamships RAG API — Day 3

> Part of the Steamships Odoo Prototype, Day 3 "the brain".
> Plan: `~/.claude/plans/shiny-mixing-wren.md`
> Mock data: `../mock_data/rag_documents/`

A small FastAPI service that ingests the Steamships mock documents into a
local ChromaDB collection and exposes a retrieval endpoint. Used by the Day 4
chat UI to find the right chunks before the LLM (not in this repo yet) writes
the final answer.

## Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` | Local, no API key, 384 dims, fast |
| Vector store | ChromaDB `PersistentClient` | Embedded mode keeps the stack at 1 service |
| API | FastAPI 0.115 + uvicorn | Lightweight, matches the plan's middleware role |
| Chunking | paragraph-aware, 800 chars / 100 overlap | Matches `MANIFEST_ingestion_metadata.json` |
| Container | `python:3.11-slim` | Separate from the Odoo image to keep wheel caches clean |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/healthz` | Liveness + collection stats |
| GET  | `/api/collections/stats` | Collection size and embedding model name |
| POST | `/api/ingest` | Re-run the full ingest (upsert; idempotent) |
| POST | `/api/retrieve` | `{"question","mode":"STAFF\|CLIENT","top_k":5}` → top-K chunks |

## Quick start

```bash
# 1. Build and start the stack.
docker compose up -d --build rag-api

# 2. Wait for the healthcheck, then check.
curl -fsS http://localhost:9000/api/healthz
# {"status":"ok","embedding_model":"sentence-transformers/all-MiniLM-L6-v2",
#  "collection_name":"steamships_rag","chunk_count":0}

# 3. Seed the collection (re-runnable).
docker compose exec rag-api python -m app.scripts.seed
# Inserted N chunks across 17 documents. Collection: steamships_rag.

# 4. Confirm the collection is populated.
curl -fsS http://localhost:9000/api/collections/stats

# 5. Run the smoke test against the demo Scene 2 questions.
docker compose exec rag-api python -m app.scripts.smoke_query
```

## Manual query examples

Star question (Demo Scene 2 — "THE STAR"):

```bash
curl -sS -X POST http://localhost:9000/api/retrieve \
  -H 'Content-Type: application/json' \
  -d '{
        "question": "A client wants to ship a 20ft container from Lae to Port Moresby — what do I quote and what documents do I need?",
        "mode": "STAFF",
        "top_k": 5
      }' | python -m json.tool
```

Expected: top chunks include `PRICELIST-2026-Q2` (price) and `SOP-SHIP-004`
(documents).

Honesty question (out of corpus):

```bash
curl -sS -X POST http://localhost:9000/api/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"question":"What was the Q1 2026 revenue for Steamships Hospitality division?","mode":"STAFF","top_k":5}' \
  | python -m json.tool
```

Expected: low scores across the top-5 (no relevant docs in the corpus).
This is the basis for the LLM's "I do not know" answer — to be wired in Day 4.

CLIENT mode filter check:

```bash
curl -sS -X POST http://localhost:9000/api/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"question":"How much does it cost to ship a container?","mode":"CLIENT","top_k":5}' \
  | python -m json.tool
```

Expected: `chunks: []` — no CLIENT docs mention prices.

## Re-seeding

The seed script uses Chroma's `upsert` keyed by `chunk_id`
(`sha1(doc_id|chunk_index)[:12]`). Running it a second time overwrites existing
vectors instead of duplicating them — verified by step 8 of the plan.

If you change the manifest or chunking strategy and want a clean rebuild:

```bash
docker compose down rag-api
rm -rf chroma_data/
docker compose up -d --build rag-api
docker compose exec rag-api python -m app.scripts.seed
```

## File map

```
rag/
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── README.md
└── app/
    ├── __init__.py
    ├── config.py        # env -> Settings dataclass
    ├── schemas.py       # Pydantic request/response models
    ├── manifest.py      # loads MANIFEST_ingestion_metadata.json
    ├── ingest.py        # load -> chunk -> embed -> upsert
    ├── retrieve.py      # embed question -> query -> filter -> score
    ├── main.py          # FastAPI app + lifespan
    └── scripts/
        ├── __init__.py
        ├── seed.py
        └── smoke_query.py
```

## Not in this repo

- LLM answer synthesis (Claude API or mock template) — Day 4.
- Odoo backend chat UI — Day 4.
- Anthropic Voyage embeddings — switch only if/when an API key is available.
- Production hardening (auth, rate limiting, secrets, observability).
