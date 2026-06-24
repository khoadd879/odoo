"""Seed the Chroma collection from mock_data/rag_documents.

Run inside the container:
    docker compose exec rag-api python -m app.scripts.seed
"""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.ingest import (
    build_chunks,
    embed_chunks,
    get_or_create_collection,
    upsert_chunks,
)
from app.manifest import Manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed")


def main() -> int:
    settings = get_settings()
    logger.info("Seeding collection=%s from docs_path=%s", settings.collection_name, settings.docs_path)

    manifest = Manifest.load(settings.manifest_path)
    chunks = build_chunks(
        docs_path=settings.docs_path,
        manifest=manifest,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        logger.warning("No chunks produced. Check docs_path=%s and manifest.", settings.docs_path)
        return 1

    collection = get_or_create_collection(settings.chroma_path, settings.collection_name)
    logger.info("Loading embedding model %s ...", settings.embedding_model)
    model = SentenceTransformer(settings.embedding_model)
    logger.info("Embedding %d chunks ...", len(chunks))
    embed_chunks(chunks, model=model)

    # Clean orphans: any chunk in the collection whose chunk_id is not in the
    # newly produced set. Covers both cases — file removed from manifest (delete
    # by filename) AND chunk added/removed/edited in an existing file (chunk_id
    # is sha1(doc_id|chunk_index) so any shift invalidates the trailing ids).
    new_ids = {c.chunk_id for c in chunks}
    raw = collection.get(include=["metadatas"])
    existing_ids = raw.get("ids", [])
    existing_metas = raw.get("metadatas", [])
    orphan_ids = [
        cid
        for cid, meta in zip(existing_ids, existing_metas)
        if cid not in new_ids and meta.get("filename", "") in {c.filename for c in chunks}
    ]
    # Plus any chunks whose filename is no longer in the manifest at all.
    source_filenames = {c.filename for c in chunks}
    for cid, meta in zip(existing_ids, existing_metas):
        if meta.get("filename", "") not in source_filenames and cid not in orphan_ids:
            orphan_ids.append(cid)
    if orphan_ids:
        logger.info("Removing %d orphan chunks from previous seed(s)", len(orphan_ids))
        collection.delete(ids=orphan_ids)

    inserted = upsert_chunks(chunks, collection)

    documents_processed = len({c.filename for c in chunks})
    print(f"Inserted {inserted} chunks across {documents_processed} documents. Collection: {settings.collection_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
