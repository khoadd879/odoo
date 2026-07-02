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

    sources = list(dict.fromkeys(c.doc_name for c in chunks if c.doc_name))

    return RetrieveResponse(
        question=req.question,
        mode=req.mode,
        chunks=chunks,
        answer=answer,
        sources=sources,
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
