FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PRELOAD_EMBEDDING_MODEL=false

# System packages:
#  - build-essential / gcc / python3-dev: Chroma's onnxruntime + hnswlib
#    native extensions.
#  - poppler-utils: PDF rendering (OCR path).
#  - libgl1 / libglib2.0-0: PIL wheels that link against libGL.
#  - tesseract-ocr: kept in case we fall back to local OCR during tests.
#  - curl: healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        python3-dev \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Pre-download the embedding model only when explicitly requested.
# Building the model at image-build time is fine on a fat local build, but
# it regularly times out or OOMs on Railway / Render free tiers, so we keep
# it opt-in. The sentence-transformers library caches the model in
# ~/.cache/huggingface and downloads on first use by default.
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "true" ]; then \
        python -c "from sentence_transformers import SentenceTransformer; \
            SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"; \
    fi

COPY app /app/app

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-9000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
