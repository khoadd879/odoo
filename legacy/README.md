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