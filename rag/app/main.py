"""FastAPI entry point.

Lifespan warms up the embedding model and the Chroma collection once. Routes:
    GET  /api/healthz
    GET  /api/collections/stats
    POST /api/ingest         (re-run ingest; upserts)
    POST /api/retrieve       (the demo star endpoint)
"""

from __future__ import annotations

import base64
import json
import logging
import re
from contextlib import asynccontextmanager

import fitz  # PyMuPDF
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
    DocumentAnalyzeRequest,
    DocumentAnalyzeResponse,
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


# ---------------------------------------------------------------------------
# KYC / Document Analysis
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_TEXT_EXTS = {".txt", ".csv", ".md"}
_PDF_MAX_PAGES = 3
_PDF_DPI = 150
_TEXT_MAX_CHARS = 15_000

_SYSTEM_PROMPT = (
    "Bạn là một Chuyên gia Thẩm định Hồ sơ (KYC/Compliance Officer) của Steamships "
    "Trading Company. Nhiệm vụ của bạn là đọc và phân tích tài liệu được cung cấp "
    "(Giấy phép kinh doanh, Hợp đồng, Giấy tờ tùy thân). Hãy đọc cẩn thận và trả về "
    "kết quả ĐÚNG ĐỊNH DẠNG JSON với các key: is_valid_kyc, company_name_found, "
    "has_signature, confidence_score, reasoning. TRẢ VỀ CHỈ JSON, KHÔNG CÓ MARKDOWN "
    "HOẶC TEXT NÀO KHÁC."
)


def _split_ext(filename: str) -> str:
    """Return the lowercase extension including the leading dot, e.g. '.pdf'."""
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _prepare_content_for_llm(
    filename: str, file_bytes: bytes
) -> tuple[list[dict], str | None]:
    """Route the uploaded file to the right shape for the OpenAI chat completion.

    Returns ``(content_parts, plain_text_or_none)``:
      - ``content_parts`` is the OpenAI ``user.content`` payload — a list of dicts
        mixing ``image_url`` and ``text`` parts.
      - ``plain_text_or_none`` is the decoded text when the file is a text file
        (used to append into the user prompt), otherwise ``None``.
    """
    ext = _split_ext(filename)

    if ext in _IMAGE_EXTS:
        mime = "image/png" if ext == ".png" else "image/jpeg"
        if ext == ".webp":
            mime = "image/webp"
        data_url = f"data:{mime};base64,{base64.b64encode(file_bytes).decode('ascii')}"
        return (
            [{"type": "image_url", "image_url": {"url": data_url}}],
            None,
        )

    if ext == ".pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises a variety of errors on bad PDFs
            raise HTTPException(status_code=400, detail=f"Invalid PDF: {exc}") from exc

        parts: list[dict] = []
        zoom = _PDF_DPI / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        try:
            for page_index in range(min(len(doc), _PDF_MAX_PAGES)):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    }
                )
        finally:
            doc.close()
        return parts, None

    if ext in _TEXT_EXTS:
        try:
            text = file_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Cannot decode text file: {exc}") from exc
        if len(text) > _TEXT_MAX_CHARS:
            text = text[:_TEXT_MAX_CHARS]
        return [{"type": "text", "text": text}], text

    raise HTTPException(status_code=400, detail="Unsupported file format")


@app.post("/api/analyze-document", response_model=DocumentAnalyzeResponse)
def analyze_document(req: DocumentAnalyzeRequest) -> DocumentAnalyzeResponse:
    """Run a Vision LLM over an uploaded KYC document and return a structured verdict."""
    # 1. Decode the base64 payload.
    try:
        file_bytes = base64.b64decode(req.file_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 payload: {exc}") from exc

    # 2. Route the file to the right shape (images, PDF pages, or text).
    content_parts, plain_text = _prepare_content_for_llm(req.filename, file_bytes)

    # 3. Build the user prompt — append expected_company_name if provided.
    user_prompt = "Hãy phân tích tài liệu sau đây."
    if req.expected_company_name:
        user_prompt += (
            f" Đặc biệt hãy xác minh tên công ty: \"{req.expected_company_name}\"."
        )

    # The text file case already inlined the document text into content_parts;
    # in that case the user prompt is just the directive. For images / PDFs we
    # put the directive first so the model treats the file as evidence.
    if plain_text is None:
        user_content: list[dict] = [{"type": "text", "text": user_prompt}] + content_parts
    else:
        user_content = [{"type": "text", "text": f"{user_prompt}\n\n---\n{plain_text}\n---"}]

    # 4. Call the OpenAI-compatible client. Force JSON output.
    settings: Settings = app.state.settings
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )

    try:
        completion = client.chat.completions.create(
            model=getattr(settings, "openai_model", "gpt-4o-mini") or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("LLM call failed for analyze-document")
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}") from exc

    # 5. Parse the JSON verdict and return it.
    try:
        payload = json.loads(raw)
    except Exception as exc:
        logger.exception("LLM returned non-JSON for analyze-document: %r", raw)
        raise HTTPException(status_code=500, detail=f"LLM returned non-JSON output: {exc}") from exc

    try:
        return DocumentAnalyzeResponse(
            is_valid_kyc=bool(payload.get("is_valid_kyc", False)),
            company_name_found=str(payload.get("company_name_found", "")),
            has_signature=bool(payload.get("has_signature", False)),
            confidence_score=int(payload.get("confidence_score", 0)),
            reasoning=str(payload.get("reasoning", "")),
        )
    except Exception as exc:
        logger.exception("LLM JSON did not match DocumentAnalyzeResponse: %r", payload)
        raise HTTPException(status_code=500, detail=f"Invalid LLM response shape: {exc}") from exc
