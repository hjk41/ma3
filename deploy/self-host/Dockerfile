# syntax=docker/dockerfile:1
# Build from repo root:
#   docker build -f deploy/self-host/Dockerfile .
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY code/server/requirements.txt .
# Embeddings need torch via sentence-transformers, but default PyPI torch is the
# CUDA wheel (+ NCCL/cuDNN, ~1GB+). Self-host MiniLM runs on CPU — install the
# CPU index first so the later requirements install does not pull GPU libs.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch>=2.2,<3" \
 && pip install --no-cache-dir -r requirements.txt

COPY code/server/app ./app
COPY code/server/scripts ./scripts
# client_bundle resolves CLIENT_DIR as parents[3]/client → /client in this image layout
COPY code/client /client

ENV PYTHONUNBUFFERED=1 \
    MA3_BOOTSTRAP_KEY_FILE=/data/bootstrap_api_key.txt \
    MA3_HF_HOME=/data/hf \
    HF_HOME=/data/hf

RUN mkdir -p /data/hf/hub

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app"]
