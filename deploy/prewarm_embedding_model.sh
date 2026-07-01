#!/usr/bin/env bash
# Download/cache the sentence-transformer model before uvicorn starts.
# Requires outbound HTTPS (use home proxy on LAN if needed).
set -euo pipefail

MA3_DIR="${MA3_DIR:-/home/hct/ma3}"
HF_HOME="${MA3_HF_HOME:-${MA3_DIR}/data/hf-cache}"
export HF_HOME
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export TRANSFORMERS_CACHE="${HF_HOME}/transformers"
mkdir -p "$HF_HOME" "$HUGGINGFACE_HUB_CACHE" "$TRANSFORMERS_CACHE"

if [[ -z "${HTTP_PROXY:-}" && -z "${HTTPS_PROXY:-}" ]]; then
  export HTTP_PROXY="${MA3_HTTP_PROXY:-http://192.168.31.200:1080}"
  export HTTPS_PROXY="${MA3_HTTPS_PROXY:-http://192.168.31.200:1080}"
fi

PYTHON="${MA3_PYTHON:-${MA3_DIR}/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

echo "==> prewarm embedding model (HF_HOME=$HF_HOME)"
"$PYTHON" - <<'PY'
import os

from pathlib import Path

for key in ("HTTP_PROXY", "HTTPS_PROXY", "HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
    print(f"{key}={os.environ.get(key, '')}")

model_name = os.environ.get("MA3_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# Download weights first; SentenceTransformer alone can race httpx shutdown under proxy.
from huggingface_hub import snapshot_download

cache_dir = os.environ["HF_HOME"]
print("snapshot_download_start", model_name, flush=True)
snapshot_download(repo_id=model_name, cache_dir=cache_dir)
print("snapshot_download_done", flush=True)

# Validate cache presence; avoid loading torch here (slow, can race other downloads).
snapshots = list(Path(cache_dir).glob("**/config.json"))
if not snapshots:
    raise SystemExit("model cache missing after snapshot_download")
print("model_ok", model_name, "cache_files", len(snapshots), flush=True)
PY
