FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

# Pre-download the embedding model so the first request is fast.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app /app/app

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-9000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]