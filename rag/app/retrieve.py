"""Retrieval: embed a question, query Chroma, filter by visibility, return chunks."""

from __future__ import annotations

import logging
from typing import List

from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

from .ingest import Chunk
from .schemas import RetrievedChunk

logger = logging.getLogger(__name__)


def query_chunks(
    question: str,
    mode: str,
    top_k: int,
    collection: Collection,
    model: SentenceTransformer,
) -> List[RetrievedChunk]:
    """Return the top-K most relevant chunks filtered by `visibility == mode`.

    Chroma's `where` filter takes a flat dict; equality on `visibility`. We
    ask Chroma for `top_k * 2` and then truncate, in case the collection has
    fewer chunks than `top_k` in the requested mode (Chroma returns what it has
    in that case, so this guard is defensive).
    """
    question_vector = model.encode(
        [question],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0].tolist()

    raw = collection.query(
        query_embeddings=[question_vector],
        n_results=min(top_k, max(collection.count(), 1)),
        where={"visibility": mode},
    )

    ids = raw.get("ids", [[]])[0]
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    results: List[RetrievedChunk] = []
    for cid, doc, meta, dist in zip(ids, docs, metas, distances):
        # Chroma returns cosine DISTANCE (lower = more similar). We convert to
        # a 0-1 SCORE for the response so the UI shows "higher = better".
        score = max(0.0, 1.0 - float(dist))
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                doc_id=meta.get("doc_id", ""),
                doc_name=meta.get("doc_name", ""),
                section=meta.get("section", ""),
                division=meta.get("division", ""),
                visibility=meta.get("visibility", mode),
                filename=meta.get("filename", ""),
                chunk_index=int(meta.get("chunk_index", 0)),
                score=round(score, 4),
                text=doc,
            )
        )
    return results[:top_k]


def build_chunk_from_retrieved(chunk: RetrievedChunk) -> Chunk:
    """Adapt a RetrievedChunk back to a Chunk (for callers that want to feed
    the LLM layer later). Currently unused but kept for Day 4 wiring.
    """
    return Chunk(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_name=chunk.doc_name,
        section=chunk.section,
        division=chunk.division,
        visibility=chunk.visibility,
        tags="",
        filename=chunk.filename,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        char_start=0,
        char_end=len(chunk.text),
    )
