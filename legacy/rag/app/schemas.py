"""Pydantic schemas for the RAG API."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Visibility = Literal["STAFF", "CLIENT"]
# Frontend sends `mode` in lowercase ('staff' | 'client'). We normalise it to
# the uppercase `Visibility` value before passing it down to the retriever.
Mode = Literal["staff", "client"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    embedding_model: str
    collection_name: str
    chunk_count: int


class IngestRequest(BaseModel):
    """Optional overrides for an explicit ingest call."""

    docs_path: Optional[str] = Field(
        default=None, description="Override DOCS_PATH for this ingest call."
    )
    chunk_size: Optional[int] = Field(default=None, ge=64, le=4000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=1000)


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_inserted: int
    collection_name: str
    skipped_unchanged: bool = False


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    section: str
    division: str
    visibility: Visibility
    filename: str
    chunk_index: int
    score: float = Field(description="Cosine similarity, 0-1 (higher = more relevant).")
    text: str


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Frontend-facing mode. Lowercase 'staff' | 'client'; defaults to 'client'
    # so the safe (public-only) behaviour wins when the frontend omits the field.
    mode: Mode = "client"
    top_k: int = Field(default=5, ge=1, le=20)


class RetrieveResponse(BaseModel):
    question: str
    # Echoed back as the lowercase form the frontend sent in.
    mode: Mode
    chunks: List[RetrievedChunk]
    answer: str


class CollectionStats(BaseModel):
    collection_name: str
    chunk_count: int
    embedding_model: str


class DocumentAnalyzeRequest(BaseModel):
    """Request body for /api/analyze-document (KYC vision analysis)."""

    lead_id: int
    filename: str
    file_base64: str = Field(
        description="Base64-encoded content of the file (PDF, image, or text).",
    )
    expected_company_name: Optional[str] = None


class DocumentAnalyzeResponse(BaseModel):
    """Structured result returned by the KYC vision LLM."""

    is_valid_kyc: bool
    company_name_found: str
    has_signature: bool
    confidence_score: int = Field(ge=0, le=100)
    reasoning: str
