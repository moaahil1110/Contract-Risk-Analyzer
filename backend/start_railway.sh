#!/bin/sh
set -e

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
