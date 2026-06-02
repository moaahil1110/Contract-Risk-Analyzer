"""Celery worker entrypoint for contract analysis."""

import asyncio
import logging

from celery.signals import task_failure

from core.status import CONTRACT_STATUS_FAILED, JOB_STATUS_FAILED, JOB_STATUS_RETRYING
from db.queries import (
    create_analysis_job,
    get_active_analysis_job,
    get_analysis_job_by_task_id,
    update_analysis_job,
    update_contract_progress,
)
from services.analysis_pipeline import NonRetryablePipelineError, run_contract_analysis_sync
from services.job_queue import celery_app

logger = logging.getLogger(__name__)


if celery_app is not None:

    async def _mark_lost_task_failed(task_id: str, error: str) -> None:
        job = await get_analysis_job_by_task_id(task_id)
        if not job:
            logger.error("Failed task had no matching analysis job: %s", task_id)
            return

        contract_id = job.get("contract_id")
        await update_analysis_job(
            job["id"],
            JOB_STATUS_FAILED,
            stage=CONTRACT_STATUS_FAILED,
            error=error,
            celery_task_id=task_id,
        )
        if contract_id:
            await update_contract_progress(
                contract_id,
                CONTRACT_STATUS_FAILED,
                100,
                "Analysis worker failed",
                error,
            )

    @task_failure.connect
    def mark_failed_task(sender=None, task_id=None, exception=None, **_kwargs):
        if sender and getattr(sender, "name", None) != "worker.analyse_contract_task":
            return
        if not task_id:
            return

        error = str(exception) if exception else "Analysis worker failed unexpectedly"
        try:
            asyncio.run(_mark_lost_task_failed(task_id, error))
        except Exception:
            logger.exception("Failed to persist Celery task failure for task %s", task_id)

    @celery_app.task(
        bind=True,
        name="worker.analyse_contract_task",
        autoretry_for=(RuntimeError, ConnectionError, TimeoutError),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
    )
    def analyse_contract_task(self, contract_id: str):
        task_id = self.request.id
        active_job = None

        try:
            active_job = asyncio.run(get_active_analysis_job(contract_id))
            if not active_job:
                active_job = asyncio.run(create_analysis_job(contract_id, task_id, max_retries=self.max_retries or 3))
            elif active_job.get("celery_task_id") != task_id:
                asyncio.run(update_analysis_job(active_job["id"], active_job["status"], celery_task_id=task_id))

            return run_contract_analysis_sync(
                contract_id=contract_id,
                job_id=active_job.get("id") if active_job else None,
                celery_task_id=task_id,
                attempt=(self.request.retries or 0) + 1,
            )
        except NonRetryablePipelineError:
            raise
        except Exception as exc:
            if active_job:
                asyncio.run(update_analysis_job(
                    active_job["id"],
                    JOB_STATUS_RETRYING if self.request.retries < (self.max_retries or 3) else JOB_STATUS_FAILED,
                    stage="retrying",
                    attempts=(self.request.retries or 0) + 1,
                    error=str(exc),
                    celery_task_id=task_id,
                ))
            logger.exception("Celery analysis task failed")
            raise
