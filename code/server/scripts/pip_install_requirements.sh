#!/usr/bin/env bash
# Install server requirements with CPU-only torch first.
# Default PyPI torch resolves to CUDA wheels (~GBs of nvidia-*), which
# exhausts GitHub Actions runners (Errno 28). Same approach as
# deploy/self-host/Dockerfile.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<3"
python -m pip install -r requirements.txt "$@"
