"""FastAPI entry point.

Lifespan warms up the embedding model and the Chroma collection once. Routes:
    GET  /api/healthz
    GET  /api/collections/stats
    POST /api/ingest         (re-run ingest; upserts)
    POST /api/retrieve       (the demo star endpoint)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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
    """Return top-K chunks filtered by visibility (STAFF or CLIENT)."""
    chunks = query_chunks(
        question=req.question,
        mode=req.mode,
        top_k=req.top_k,
        collection=app.state.collection,
        model=app.state.model,
    )
    return RetrieveResponse(question=req.question, mode=req.mode, chunks=chunks)
