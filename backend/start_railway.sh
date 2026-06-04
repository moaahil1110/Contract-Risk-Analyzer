#!/bin/sh
set -e

if [ "${RUN_WORKER_IN_WEB:-true}" = "true" ]; then
  celery -A worker.celery_app worker \
    --loglevel="${CELERY_LOGLEVEL:-INFO}" \
    --pool="${CELERY_WORKER_POOL:-solo}" \
    --concurrency="${CELERY_WORKER_CONCURRENCY:-1}" &
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
