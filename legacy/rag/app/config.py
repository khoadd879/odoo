"""Runtime configuration for the RAG API.

All values come from environment variables so the same image runs unchanged in
local docker-compose, CI, and (eventually) production. Defaults match the
docker-compose service definition.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the runtime configuration."""

    chroma_path: str
    collection_name: str
    embedding_model: str
    docs_path: str
    manifest_path: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    openai_api_key: str
    openai_base_url: str
    openai_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            chroma_path=os.environ.get("CHROMA_PATH", "/data/chroma"),
            collection_name=os.environ.get("COLLECTION_NAME", "steamships_rag"),
            embedding_model=os.environ.get(
                "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            docs_path=os.environ.get("DOCS_PATH", "/docs/mock/rag_documents"),
            manifest_path=os.environ.get(
                "MANIFEST_PATH", "/docs/mock/rag_documents/MANIFEST_ingestion_metadata.json"
            ),
            chunk_size=_int_env("CHUNK_SIZE", 800),
            chunk_overlap=_int_env("CHUNK_OVERLAP", 100),
            top_k=_int_env("TOP_K", 5),
            openai_api_key=os.environ.get("GROQ_API_KEY", ""),
            openai_base_url=os.environ.get(
                "OPENAI_BASE_URL", "https://api.groq.com/openai/v1"
            ),
            openai_model=os.environ.get("OPENAI_MODEL", "llama-3.3-70b-versatile"),
        )


def get_settings() -> Settings:
    """Read settings on every call so tests can monkey-patch the environment."""
    return Settings.from_env()
