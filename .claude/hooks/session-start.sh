#!/bin/bash
# SessionStart hook for Claude Code cloud sessions.
# Installs system packages, backend Python deps (Python 3.11 venv, CPU torch),
# frontend npm deps, and the offline embedding model used by the RAG eval.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VENV="$ROOT/.venv"
MODEL_PATH="$HOME/.cache/models/all-MiniLM-L6-v2"

# System libraries for OCR (tesseract) and PDF export (WeasyPrint), matching CI.
if ! command -v tesseract >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq tesseract-ocr tesseract-ocr-eng poppler-utils \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 libcairo2 \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev \
    shared-mime-info >/dev/null
fi

# Backend: Python 3.11 (same as CI/Docker); pinned deps lack 3.13 wheels.
if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python python3.11 "$VENV"
fi
uv pip install --quiet --python "$VENV/bin/python" \
  --index-url https://download.pytorch.org/whl/cpu torch==2.3.1
uv pip install --quiet --python "$VENV/bin/python" -r "$ROOT/backend/requirements.txt"

# Offline embedding model for build_benchmarks.py / run_rag_eval.py.
if [ ! -f "$MODEL_PATH/config.json" ]; then
  "$VENV/bin/python" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2').save('$MODEL_PATH')" \
    || echo "warning: could not download embedding model" >&2
fi

# Frontend
(cd "$ROOT/frontend" && npm install --no-audit --no-fund --loglevel=error)

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$VENV\""
    echo "export PATH=\"$VENV/bin:\$PATH\""
    echo "export EMBEDDING_MODEL_PATH=\"$MODEL_PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi
