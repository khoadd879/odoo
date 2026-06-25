FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: build-essential / python3-dev are required for Chroma's native
# extensions (onnxruntime, hnswlib). curl is for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        python3-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY rag/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Pre-download the embedding model during build so the first request is fast.
# Runs at build time; the model lands in /root/.cache/huggingface.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY rag/app /app/app
COPY rag/scripts /app/app/scripts

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:9000/api/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
