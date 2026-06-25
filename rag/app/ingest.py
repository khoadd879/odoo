"""Ingestion pipeline: load markdown -> chunk -> embed -> upsert into Chroma.

Chunking follows the manifest config (default 800 chars / 100 overlap) with a
paragraph-aware strategy: split on blank lines, carry the first markdown header
into every chunk produced in that block, then greedy-merge paragraphs up to
`chunk_size`. Each chunk gets a stable `chunk_id` derived from the doc_id and
chunk index so re-runs upsert in place instead of duplicating.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

import chromadb
from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

from .manifest import Manifest

logger = logging.getLogger(__name__)

# Chroma's `where` filter requires flat string/int/bool values. We join lists
# with commas so retrieval can still match a single tag by substring if needed.
META_LIST_JOIN = ","


@dataclass
class Chunk:
    """A single chunk ready for embedding."""

    chunk_id: str
    doc_id: str
    doc_name: str
    section: str
    division: str
    visibility: str
    tags: str
    filename: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    # Filled in by embed_chunks():
    embedding: List[float] = field(default_factory=list)


def _file_md(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        return fh.read()


def _split_paragraphs(md: str) -> List[tuple[str, int]]:
    """Return (paragraph_text, char_offset) tuples split on blank lines.

    Header lines (`#`, `##`, ...) stay attached to their own paragraph and are
    treated as the leading text of the next non-empty paragraph so they prefix
    every emitted chunk in that block.
    """
    paragraphs: List[tuple[str, int]] = []
    offset = 0
    for raw_block in md.split("\n\n"):
        stripped = raw_block.strip()
        if not stripped:
            offset += len(raw_block) + 2
            continue
        paragraphs.append((stripped, offset))
        offset += len(raw_block) + 2
    return paragraphs


def _carry_header(block: str, current_header: str) -> tuple[str, str]:
    """If `block` starts with a markdown header, return (block, new_header).

    Otherwise return (block prefixed with current_header, current_header).
    """
    first_line = block.split("\n", 1)[0].strip()
    if first_line.startswith("#"):
        return block, first_line
    if current_header:
        return f"{current_header}\n\n{block}", current_header
    return block, current_header


def chunk_text(text: str, doc_id: str, chunk_size: int, chunk_overlap: int) -> List[Chunk]:
    """Paragraph-aware chunker.

    Each chunk fits under `chunk_size` characters. We carry the first header
    into every chunk produced in that header block (per the manifest strategy)
    and prepend the last `chunk_overlap` characters of the previous chunk to the
    next one for retrieval continuity.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be in [0, chunk_size)")

    paragraphs = _split_paragraphs(text)
    chunks: List[Chunk] = []
    buffer = ""
    buffer_offset = 0
    current_header = ""
    chunk_index = 0
    last_tail = ""

    def flush(buf: str, char_start: int) -> None:
        nonlocal chunk_index, last_tail
        if not buf.strip():
            return
        chunk_id = hashlib.sha1(f"{doc_id}|{chunk_index}".encode("utf-8")).hexdigest()[:12]
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                doc_name="",  # filled in by build_chunks
                section="",  # filled in by build_chunks
                division="",  # filled in by build_chunks
                visibility="STAFF",  # default; overridden by manifest
                tags="",  # filled in by build_chunks
                filename="",  # filled in by build_chunks
                chunk_index=chunk_index,
                text=buf.strip(),
                char_start=char_start,
                char_end=char_start + len(buf.strip()),
            )
        )
        chunk_index += 1
        last_tail = buf.strip()[-chunk_overlap:] if chunk_overlap else ""

    for paragraph, para_offset in paragraphs:
        paragraph, current_header = _carry_header(paragraph, current_header)

        if not buffer:
            buffer_offset = para_offset

        # Try to add the paragraph to the current buffer.
        candidate = (buffer + "\n\n" + paragraph) if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        # Buffer would overflow — flush, then start a new buffer.
        # If a single paragraph is itself longer than chunk_size, hard-split it.
        if not buffer:
            for slice_start in range(0, len(paragraph), chunk_size):
                slice_text = paragraph[slice_start : slice_start + chunk_size]
                flush(slice_text, para_offset + slice_start)
            buffer = ""
            continue

        flush(buffer, buffer_offset)
        # Start the next buffer with overlap + current paragraph.
        overlap_prefix = last_tail
        next_buf = (overlap_prefix + "\n\n" + paragraph) if overlap_prefix else paragraph
        # If still too long, hard-split the paragraph across multiple buffers.
        if len(next_buf) <= chunk_size:
            buffer = next_buf
            buffer_offset = para_offset - len(overlap_prefix) if overlap_prefix else para_offset
        else:
            buffer = ""
            for slice_start in range(0, len(paragraph), chunk_size):
                slice_text = paragraph[slice_start : slice_start + chunk_size]
                # Only carry overlap on the first slice after a flush.
                prefix = overlap_prefix if slice_start == 0 else ""
                full = (prefix + "\n\n" + slice_text) if prefix else slice_text
                flush(full, para_offset + slice_start - len(prefix) if prefix else para_offset + slice_start)
                overlap_prefix = ""

    # Flush the trailing buffer.
    if buffer.strip():
        flush(buffer, buffer_offset)

    return chunks


def load_documents(docs_path: str | Path, manifest: Manifest) -> Iterable[tuple[Path, str, dict]]:
    """Yield (path, doc_id, manifest_entry_or_empty_dict) for every .md file.

    The manifest entry is empty when the file is not listed there (we still
    ingest it but tag it as visibility=STAFF by default).
    """
    root = Path(docs_path)
    if not root.exists():
        raise FileNotFoundError(f"docs_path does not exist: {root}")

    md_files = sorted(p for p in root.glob("*.md") if not p.name.startswith("."))
    for path in md_files:
        entry = manifest.get(path.name) or {}
        doc_id = entry.get("doc_id") or path.stem
        yield path, doc_id, entry


def build_chunks(docs_path: str | Path, manifest: Manifest, chunk_size: int, chunk_overlap: int) -> List[Chunk]:
    """Load every .md under docs_path, chunk, and stamp manifest metadata."""
    all_chunks: List[Chunk] = []
    for path, doc_id, entry in load_documents(docs_path, manifest):
        text = _file_md(path)
        chunks = chunk_text(text, doc_id, chunk_size, chunk_overlap)
        for chunk in chunks:
            chunk.doc_name = entry.get("doc_name") or doc_id
            chunk.section = entry.get("section") or "Uncategorised"
            chunk.division = entry.get("division") or "Group"
            chunk.visibility = entry.get("visibility") or "STAFF"
            chunk.tags = META_LIST_JOIN.join(entry.get("tags", []))
            chunk.filename = path.name
        all_chunks.extend(chunks)
        logger.info("Chunked %s -> %d chunks", path.name, len(chunks))
    return all_chunks


def embed_chunks(chunks: Sequence[Chunk], model: SentenceTransformer, batch_size: int = 32) -> None:
    """Embed all chunks in-place. Mutates each chunk's `.embedding` field."""
    if not chunks:
        return
    texts = [c.text for c in chunks]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,  # cosine via dot product
        convert_to_numpy=True,
    )
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector.tolist()


def get_or_create_collection(chroma_path: str, collection_name: str) -> Collection:
    """Return the named collection, creating it if absent."""
    os.makedirs(chroma_path, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks: Sequence[Chunk], collection: Collection) -> int:
    """Upsert chunks into the collection. Returns count of upserted rows.

    Chroma's `upsert` matches by `id`, so re-running the seed overwrites
    existing vectors instead of duplicating them (idempotent — required by the
    plan's verification step 8).
    """
    if not chunks:
        return 0
    ids = [c.chunk_id for c in chunks]
    embeddings = [c.embedding for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [
        {
            "doc_id": c.doc_id,
            "doc_name": c.doc_name,
            "section": c.section,
            "division": c.division,
            "visibility": c.visibility,
            "tags": c.tags,
            "filename": c.filename,
            "chunk_index": c.chunk_index,
        }
        for c in chunks
    ]
    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return len(chunks)
