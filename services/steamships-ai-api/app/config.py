"""Runtime configuration for the steamships-ai-api FastAPI service.

All values come from environment variables so the same image runs unchanged
locally (docker compose), on Railway/Render, and on a VPS. pydantic-settings
keeps the load order predictable and gives type coercion + validation for
free.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, List, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class _AllowOriginsCsvSource(EnvSettingsSource):
    """EnvSettingsSource that handles allowed_origins as comma-separated string.

    pydantic-settings marks List[str] fields as "complex" and calls json.loads()
    on the raw env value before field validators run, which fails for
    comma-separated strings like "http://a,http://b". This subclass intercepts
    the prepare_field_value call for that specific field and splits on commas.
    """

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name == "allowed_origins" and isinstance(value, str) and value:
            # Split comma-separated origins instead of JSON-decoding
            return [item.strip() for item in value.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    """Immutable snapshot of the runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    port: int = Field(default=9000, ge=1, le=65535)

    # Auth — empty means no token required (local dev default).
    ai_api_token: str = Field(default="", alias="AI_API_TOKEN")

    # Vector store
    vector_backend: str = Field(default="chroma", alias="VECTOR_BACKEND")
    chroma_path: str = Field(default="/data/chroma", alias="CHROMA_PATH")
    collection_name: str = Field(default="steamships_rag", alias="COLLECTION_NAME")
    docs_path: str = Field(
        default="/docs/mock/rag_documents", alias="DOCS_PATH"
    )
    manifest_path: str = Field(
        default="/docs/mock/rag_documents/MANIFEST_ingestion_metadata.json",
        alias="MANIFEST_PATH",
    )

    # Chunking / retrieval
    chunk_size: int = Field(default=800, ge=64, le=4000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, ge=0, le=1000, alias="CHUNK_OVERLAP")
    top_k: int = Field(default=5, ge=1, le=20, alias="TOP_K")

    # Embedding
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )

    # LLM (OpenAI-compatible; Groq is the default backend).
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="", alias="OPENAI_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    # OCR
    ocr_model: str = Field(default="", alias="OCR_MODEL")

    # CORS — comma-separated env var (e.g. "http://localhost:8069,http://localhost:9000").
    # _AllowOriginsCsvSource splits this on commas before pydantic decodes it as List[str].
    allowed_origins: List[str] = Field(default_factory=list)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_class: type["Settings"],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Replace EnvSettingsSource with our _AllowOriginsCsvSource subclass.

        The subclass handles the allowed_origins comma-separated string correctly
        instead of failing JSON decode. All other fields are unchanged.
        """
        # Instantiate our subclass using the same settings as the passed env_settings.
        return (
            _AllowOriginsCsvSource(
                settings_cls=env_settings.settings_cls,
                case_sensitive=env_settings.case_sensitive,
                env_prefix=env_settings.env_prefix,
                env_prefix_target=env_settings.env_prefix_target,
                env_nested_delimiter=env_settings.env_nested_delimiter,
                env_nested_max_split=env_settings.env_nested_max_split,
                env_ignore_empty=env_settings.env_ignore_empty,
                env_parse_none_str=env_settings.env_parse_none_str,
                env_parse_enums=env_settings.env_parse_enums,
            ),
        )

    @property
    def auth_required(self) -> bool:
        """True when AI_API_TOKEN is configured — endpoints must enforce it."""
        return bool(self.ai_api_token)

    @property
    def llm_api_key(self) -> str:
        """Resolve the effective API key for the LLM client (OPENAI > GROQ)."""
        return self.openai_api_key or self.groq_api_key

    @property
    def llm_base_url(self) -> str:
        """Default to Groq when OPENAI_BASE_URL is unset."""
        return self.openai_base_url or "https://api.groq.com/openai/v1"

    @property
    def llm_model(self) -> str:
        """Default to the Groq llama-3.3 70B when OPENAI_MODEL is unset."""
        return self.openai_model or "llama-3.3-70b-versatile"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Tests that need fresh values should clear the cache with
    ``get_settings.cache_clear()`` after patching the environment.
    """
    return Settings()
