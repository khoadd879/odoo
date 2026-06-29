"""Retrieval: embed a question, query Chroma, filter by visibility, return chunks."""

from __future__ import annotations

import logging
from typing import List, Optional

from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

from .ingest import Chunk
from .schemas import RetrievedChunk

logger = logging.getLogger(__name__)

# Frontend-facing modes (lowercase). The retrieve layer normalises them to the
# uppercase `Visibility` values stored in Chroma.
MODE_STAFF = "staff"
MODE_CLIENT = "client"

# Sections / tags considered internal-only and excluded from the client view.
# Mirrors the manifest conventions in mock_data/rag_documents/MANIFEST_*.json.
_CLIENT_EXCLUDED_SECTIONS = ("Pricing",)  # any section ending with " SOPs" is excluded too
_CLIENT_EXCLUDED_SECTION_SUFFIXES = (" SOPs",)
_CLIENT_EXCLUDED_TAGS = ("pricing", "price-list")


def _build_where_filter(mode: str) -> Optional[dict]:
    """Build the Chroma `where` filter for a given frontend `mode`.

    - `staff`: no extra metadata filter — staff can see everything, including
      STAFF-only chunks (internal SOPs, pricing, etc.).
    - `client`: only public/onboarding chunks. We enforce three exclusions:
        1. `visibility` must be `CLIENT` (manifest-level access flag).
        2. `section` must NOT be `Pricing`.
        3. `section` must NOT end with ` SOPs` (catches "Shipping SOPs",
           "HR SOPs", "Finance SOPs", etc. without enumerating each one).

    The list of conditions lives in two small tuples above so the rule stays
    data-driven when new sections are added to the manifest.
    """
    if mode == MODE_STAFF:
        return None

    # Client mode: restrict to CLIENT visibility AND exclude pricing / SOPs.
    # Chroma's `where` supports `$ne` / `$not` / `$nin` for these exclusions.
    return {
        "$and": [
            {"visibility": "CLIENT"},
            {"section": {"$ne": _CLIENT_EXCLUDED_SECTIONS[0]}},
            # `section` does not end with any of the internal-suffixed patterns.
            # Chroma only supports a flat $ne equality, so we OR the equality
            # for each candidate suffix via $not.
            {"section": {"$not": _CLIENT_EXCLUDED_SECTION_SUFFIXES[0]}},
        ]
    }


def query_chunks(
    question: str,
    mode: str,
    top_k: int,
    collection: Collection,
    model: SentenceTransformer,
) -> List[RetrievedChunk]:
    """Return the top-K most relevant chunks, filtered according to `mode`.

    `mode` is the frontend-facing value: `'staff'` (full access) or
    `'client'` (onboarding / public docs only — SOPs and Pricing excluded).

    Staff mode applies no metadata filter on top of the semantic search. Client
    mode restricts the candidate set to CLIENT-visible chunks whose `section`
    is neither `Pricing` nor any `* SOPs` section (see `_build_where_filter`).
    We over-fetch slightly so the response stays full even when the collection
    has fewer matching chunks than `top_k`.
    """
    where_filter = _build_where_filter(mode)

    question_vector = model.encode(
        [question],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )[0].tolist()

    query_kwargs = {
        "query_embeddings": [question_vector],
        "n_results": min(top_k, max(collection.count(), 1)),
    }
    if where_filter is not None:
        query_kwargs["where"] = where_filter

    raw = collection.query(**query_kwargs)

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
                visibility=meta.get("visibility", mode.upper()),
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
