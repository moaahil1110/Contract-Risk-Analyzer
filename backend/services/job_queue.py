"""Celery queue integration with a test/dev-safe fallback."""

import os
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from redis import Redis

try:
    from celery import Celery
except Exception:  # pragma: no cover - exercised when dependency is absent locally
    Celery = None  # type: ignore

from core.status import ACTIVE_JOB_STATUSES

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
CELERY_DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE", "celery")

# macOS + prefork + ML libraries such as PyTorch/Chroma can abort child
# processes after fork. Keep local/dev stable by default while preserving
# prefork throughput for Linux production deploys.
def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def default_worker_pool(dev_mode: bool = DEV_MODE) -> str:
    return "solo" if dev_mode else "prefork"


def default_worker_concurrency(dev_mode: bool = DEV_MODE) -> int:
    return 1 if dev_mode else _positive_int_env("WEB_CONCURRENCY", 2)


CELERY_WORKER_POOL = os.getenv("CELERY_WORKER_POOL", default_worker_pool())
CELERY_WORKER_CONCURRENCY = _positive_int_env("CELERY_WORKER_CONCURRENCY", default_worker_concurrency())

local_job_store: Dict[str, Dict[str, Any]] = {}


def create_celery_app():
    if Celery is None:
        return None

    app = Celery(
        "contract_risk_analyzer",
        broker=REDIS_URL,
        backend=os.getenv("CELERY_RESULT_BACKEND", REDIS_URL),
        include=["worker"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_default_queue=CELERY_DEFAULT_QUEUE,
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_always_eager=CELERY_TASK_ALWAYS_EAGER,
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            "visibility_timeout": _positive_int_env("CELERY_VISIBILITY_TIMEOUT_SECONDS", 3600),
            "socket_keepalive": True,
        },
        result_backend_transport_options={
            "visibility_timeout": _positive_int_env("CELERY_VISIBILITY_TIMEOUT_SECONDS", 3600),
        },
        worker_pool=CELERY_WORKER_POOL,
        worker_concurrency=CELERY_WORKER_CONCURRENCY,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_time_limit=_positive_int_env("CELERY_TASK_TIME_LIMIT_SECONDS", 1800),
        task_soft_time_limit=_positive_int_env("CELERY_TASK_SOFT_TIME_LIMIT_SECONDS", 1500),
    )
    return app


celery_app = create_celery_app()


def enqueue_contract_analysis(contract_id: str, task_id: str | None = None) -> str:
    task_id = task_id or str(uuid.uuid4())

    if CELERY_TASK_ALWAYS_EAGER:
        try:
            if celery_app is not None:
                from worker import analyse_contract_task

                result = analyse_contract_task.apply(args=[contract_id], task_id=task_id)
                if result.failed():
                    result.get(propagate=True)
                task_id = result.id
            else:
                from services.analysis_pipeline import run_contract_analysis_sync

                run_contract_analysis_sync(contract_id=contract_id, celery_task_id=task_id)
            if contract_id in local_job_store:
                local_job_store[contract_id].update({
                    "status": "succeeded",
                    "current_stage": "complete",
                    "progress_percent": 100,
                })
        except Exception:
            if contract_id in local_job_store:
                local_job_store[contract_id].update({
                    "status": "failed",
                    "current_stage": "failed",
                    "progress_percent": 100,
                })
            raise
        return task_id

    if celery_app is None:
        return task_id

    result = celery_app.send_task("worker.analyse_contract_task", args=[contract_id], task_id=task_id)
    return result.id


async def enqueue_contract_analysis_async(contract_id: str, task_id: str | None = None) -> str:
    task_id = task_id or str(uuid.uuid4())

    if CELERY_TASK_ALWAYS_EAGER:
        try:
            from services.analysis_pipeline import run_contract_analysis

            await run_contract_analysis(contract_id=contract_id, celery_task_id=task_id)
            if contract_id in local_job_store:
                local_job_store[contract_id].update({
                    "status": "succeeded",
                    "current_stage": "complete",
                    "progress_percent": 100,
                })
        except Exception:
            if contract_id in local_job_store:
                local_job_store[contract_id].update({
                    "status": "failed",
                    "current_stage": "failed",
                    "progress_percent": 100,
                })
            raise
        return task_id

    return enqueue_contract_analysis(contract_id, task_id)


def create_local_job(contract_id: str, task_id: str) -> Dict[str, Any]:
    job = {
        "id": f"job-{uuid.uuid4()}",
        "contract_id": contract_id,
        "celery_task_id": task_id,
        "status": "queued",
        "current_stage": "queued",
        "progress_percent": 0,
    }
    local_job_store[contract_id] = job
    return job


def get_local_active_job(contract_id: str) -> Dict[str, Any] | None:
    job = local_job_store.get(contract_id)
    if job and job.get("status") in ACTIVE_JOB_STATUSES:
        return job
    return None


def get_queue_health() -> Dict[str, Any]:
    base = {
        "worker_pool": CELERY_WORKER_POOL,
        "worker_concurrency": CELERY_WORKER_CONCURRENCY,
        "task_always_eager": CELERY_TASK_ALWAYS_EAGER,
        "queue_name": CELERY_DEFAULT_QUEUE,
    }
    try:
        client = Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        health = {
            "reachable": True,
            "broker_reachable": True,
            "broker_queue_depth": client.llen(CELERY_DEFAULT_QUEUE),
            **base,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "broker_reachable": False,
            **base,
            "error": str(exc),
        }

    if celery_app is None or CELERY_TASK_ALWAYS_EAGER:
        health.update({
            "workers_online": 0,
            "worker_names": [],
            "worker_ping": {},
        })
        return health

    try:
        inspector = celery_app.control.inspect(timeout=1)
        ping = inspector.ping() or {}
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
        health.update({
            "workers_online": len(ping),
            "worker_names": sorted(ping.keys()),
            "worker_ping": ping,
            "active_task_count": sum(len(tasks) for tasks in active.values()),
            "reserved_task_count": sum(len(tasks) for tasks in reserved.values()),
            "scheduled_task_count": sum(len(tasks) for tasks in scheduled.values()),
        })
    except Exception as exc:
        health.update({
            "workers_online": 0,
            "worker_names": [],
            "worker_ping": {},
            "worker_error": str(exc),
        })
    return health
