"""FastAPI entry point.

Lifespan warms up the embedding model and the Chroma collection once. Routes:
    GET  /api/healthz
    GET  /api/collections/stats
    POST /api/ingest         (re-run ingest; upserts)
    POST /api/retrieve       (the demo star endpoint)
"""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

import markdown
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from .config import Settings, get_settings
from .ingest import (
    build_chunks,
    embed_chunks,
    get_or_create_collection,
    upsert_chunks,
)
from .manifest import Manifest
from .retrieve import query_chunks
from .schemas import (
    CollectionStats,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    RetrieveRequest,
    RetrieveResponse,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up the embedding model and the Chroma collection once at startup."""
    settings = get_settings()
    logger.info("Loading embedding model: %s", settings.embedding_model)
    app.state.settings = settings
    app.state.model = SentenceTransformer(settings.embedding_model)
    app.state.collection = get_or_create_collection(settings.chroma_path, settings.collection_name)
    app.state.manifest = Manifest.load(settings.manifest_path)
    logger.info(
        "RAG API ready (collection=%s, chunks=%d)",
        settings.collection_name,
        app.state.collection.count(),
    )
    yield


app = FastAPI(title="Steamships RAG API", version="0.1.0", lifespan=lifespan)


@app.get("/api/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        embedding_model=app.state.settings.embedding_model,
        collection_name=app.state.settings.collection_name,
        chunk_count=app.state.collection.count(),
    )


@app.get("/api/collections/stats", response_model=CollectionStats)
def collection_stats() -> CollectionStats:
    return CollectionStats(
        collection_name=app.state.settings.collection_name,
        chunk_count=app.state.collection.count(),
        embedding_model=app.state.settings.embedding_model,
    )


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest | None = None) -> IngestResponse:
    """Re-run the full ingest pipeline. Idempotent (upserts by chunk_id)."""
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


@app.post("/api/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """Retrieve top-K chunks and synthesize a natural-language answer via OpenAI."""
    chunks = query_chunks(
        question=req.question,
        mode=req.mode,
        top_k=req.top_k,
        collection=app.state.collection,
        model=app.state.model,
    )

    # Format retrieved chunks into a single context string.
    context = "\n\n".join(c.text for c in chunks) if chunks else ""

    # Initialize the OpenAI-compatible client. Groq is the default backend
    # (OPENAI_BASE_URL=https://api.groq.com/openai/v1); swap OPENAI_BASE_URL
    # to point at any other OpenAI-compatible endpoint if needed.
    settings = app.state.settings
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    system_prompt = (
        "You are a friendly and professional AI Assistant for Steamships Trading Company. "
        "Read the user's input carefully and follow these rules strictly like an IF/ELSE statement: "
        "- IF the user input is just a greeting (e.g., 'hi', 'hello', 'xin chào', 'chào bạn'): "
        "  Politely greet them back, introduce yourself as the Steamships AI Assistant, and ask how you can help them with HR, Shipping, or company policies today. DO NOT mention anything about 'context' or 'I don't know'. "
        "- ELSE IF the user asks a specific question: "
        "  Answer ONLY using the provided context. If the context does not contain the answer, politely say that you do not have that information in your current documents. "
        "ALWAYS respond in the SAME LANGUAGE that the user typed."
    )

    user_prompt = (
        f"Context:\n{context}\n\n"
        f"Question: {req.question}"
    )

    completion = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw_answer = (completion.choices[0].message.content or "").strip()

    # Some LLMs wrap their output in a ```html / ```json code fence. Strip it
    # so the markdown library sees raw Markdown, not a fenced code block.
    fence_match = re.match(r"^```(?:html|json)?\s*\n(.*)\n```\s*$", raw_answer, re.DOTALL)
    if fence_match:
        raw_answer = fence_match.group(1).strip()

    # Convert Markdown -> HTML. The output is safe to drop into an Odoo
    # HTML field; it's plain <p>/<ul>/<li>/<strong>/<h2>/<a>/etc.
    answer = markdown.markdown(
        raw_answer,
        extensions=["extra", "sane_lists"],
    )

    return RetrieveResponse(
        question=req.question,
        mode=req.mode,
        chunks=chunks,
        answer=answer,
    )
