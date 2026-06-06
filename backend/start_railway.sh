#!/bin/sh
set -e

if [ "${BUILD_BENCHMARKS_ON_START:-true}" = "true" ]; then
  echo "Ensuring benchmark vector store is populated..."
  python scripts/build_benchmarks.py
fi

if [ "${PROCESS_TYPE:-web}" = "worker" ]; then
  echo "Preparing Celery worker..."

  echo "Starting Celery worker..."
  celery -A worker.celery_app worker \
    --loglevel="${CELERY_LOGLEVEL:-INFO}" \
    --pool="${CELERY_WORKER_POOL:-solo}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-1}" &
  worker_pid="$!"
  sleep 3
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    echo "Celery worker failed to start"
    wait "$worker_pid"
    exit 1
  fi

  echo "Starting worker health server on port ${PORT:-8000}..."
  python scripts/worker_health_server.py &
  health_pid="$!"

  trap 'kill "$worker_pid" "$health_pid" 2>/dev/null || true' INT TERM
  wait "$worker_pid"
fi

if [ "${RUN_WORKER_IN_WEB:-true}" = "true" ]; then
  echo "Starting Celery worker in web container..."
  celery -A worker.celery_app worker \
    --loglevel="${CELERY_LOGLEVEL:-INFO}" \
    --pool="${CELERY_WORKER_POOL:-solo}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-1}" &
  worker_pid="$!"
  sleep 3
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    echo "Celery worker failed to start"
    wait "$worker_pid"
    exit 1
  fi
  echo "Celery worker started with PID ${worker_pid}"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
