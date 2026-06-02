#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/Caskroom/miniconda/base/envs/contract-risk/bin/python}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
REDIS_CLI="${REDIS_CLI:-redis-cli}"

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if [[ ! -d "$BACKEND_DIR" || ! -d "$FRONTEND_DIR" ]]; then
  echo "Run this script from the contract-risk-analyzer repository." >&2
  exit 1
fi

if ! command -v "$REDIS_CLI" >/dev/null 2>&1; then
  echo "redis-cli is not installed. Install Redis first: brew install redis" >&2
  exit 1
fi

if ! "$REDIS_CLI" ping >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew services start redis >/dev/null 2>&1 || true
  fi
fi

if ! "$REDIS_CLI" ping >/dev/null 2>&1; then
  if command -v redis-server >/dev/null 2>&1; then
    redis-server --daemonize yes >/dev/null 2>&1 || true
  fi
fi

if ! "$REDIS_CLI" ping >/dev/null 2>&1; then
  echo "Redis is not running. Start it with: brew services start redis" >&2
  exit 1
fi

echo "Redis: ready"

(
  cd "$BACKEND_DIR"
  "$PYTHON_BIN" -m uvicorn main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
PIDS+=("$!")
echo "Backend: http://127.0.0.1:$BACKEND_PORT"

(
  cd "$BACKEND_DIR"
  "$PYTHON_BIN" -m celery -A worker.celery_app worker --loglevel=INFO
) &
PIDS+=("$!")
echo "Worker: started"

(
  cd "$FRONTEND_DIR"
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
PIDS+=("$!")
echo "Frontend: http://localhost:$FRONTEND_PORT"

wait -n "${PIDS[@]}"
exit_code=$?
echo "A dev process exited. Shutting down the rest."
exit "$exit_code"
