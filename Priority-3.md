# Priority 3 Backend Robustness Plan

## Summary
Move contract processing out of FastAPI `BackgroundTasks` into a production-style Celery + Redis worker pipeline. Uploads will store PDFs durably in Supabase Storage, analysis will run in a separate worker, status will be persisted in Supabase, and logs will become structured enough to debug each contract, clause, retrieval call, LLM call, retry, and failure.

## Key Changes

### Queue And Worker Architecture
- Add Redis-backed Celery with separate processes:
  - FastAPI web process handles upload, auth, enqueue, status, history, export.
  - Celery worker handles PDF extraction, clause splitting, RAG retrieval, LLM analysis, scoring, and saving.
  - Optional Flower process for local/job monitoring.
- Add `backend/worker.py` or equivalent Celery app module.
- Move current `process_contract_analysis()` logic into a reusable pipeline service called by Celery, not by FastAPI.
- Queue payload must contain only durable identifiers, primarily `contract_id`; workers load contract metadata and file path from Supabase.

### Durable Upload And Status Model
- Store uploaded PDFs in Supabase Storage bucket `contracts`, path:
  - `{user_id}/{contract_id}/original.pdf`
  - In `DEV_MODE`, allow local fallback under `backend/uploads/{contract_id}/original.pdf`.
- Add migration for `contracts`:
  - `storage_path TEXT`
  - `file_size_bytes INTEGER`
  - `mime_type TEXT`
  - `status TEXT DEFAULT 'uploaded'`
  - `progress_percent INTEGER DEFAULT 0`
  - `status_message TEXT`
  - `error_message TEXT`
  - `queued_at TIMESTAMP`
  - `started_at TIMESTAMP`
  - `completed_at TIMESTAMP`
- Valid contract statuses:
  - `uploaded`
  - `queued`
  - `extracting`
  - `clauses_extracted`
  - `retrieving_benchmarks`
  - `analysing`
  - `saving_results`
  - `complete`
  - `failed`
- Add `analysis_jobs` table:
  - `id UUID`
  - `contract_id UUID`
  - `celery_task_id TEXT`
  - `status TEXT` with `queued`, `running`, `retrying`, `succeeded`, `failed`
  - `current_stage TEXT`
  - `progress_percent INTEGER`
  - `attempts INTEGER`
  - `max_retries INTEGER`
  - `last_error TEXT`
  - `timings JSONB`
  - `metadata JSONB`
  - `created_at`, `started_at`, `updated_at`, `finished_at`

### API Behavior
- `POST /upload`
  - Validate PDF.
  - Create contract row with `status='uploaded'`.
  - Store PDF in Supabase Storage.
  - Return `contract_id`, `status='uploaded'`, and `message`.
  - Do not extract clauses in the request.
- `POST /analyse/{contract_id}`
  - Verify contract exists and belongs to user.
  - If complete, return existing complete status.
  - If already queued/running, return existing job metadata.
  - Otherwise enqueue Celery task and set contract `status='queued'`.
  - Return `contract_id`, `job_id`, `task_id`, `status='queued'`.
- `GET /analyse/{contract_id}/status`
  - Return lightweight progress payload:
    - `contract_id`
    - `job_id`
    - `status`
    - `progress_percent`
    - `status_message`
    - `current_stage`
    - `has_results`
    - `error_message`
- `GET /analyse/{contract_id}`
  - Continue returning full results only when complete.
  - For non-complete states, return the same progress fields instead of generic “processing”.
- Frontend polling should use `/analyse/{contract_id}/status` for progress and navigate to results only when `has_results=true`.

### Pipeline And Observability
- Worker stage order:
  - `extracting`: download PDF, extract text.
  - `clauses_extracted`: split clauses and persist extracted text/clause count metadata.
  - `retrieving_benchmarks`: retrieve RAG evidence per clause.
  - `analysing`: call LLM per clause and persist clause-level retry/failure metadata.
  - `saving_results`: calculate health score and batch-save final results.
  - `complete`: update contract summary.
- Add helper functions:
  - `update_contract_progress(contract_id, status, progress_percent, message, error=None)`
  - `create_analysis_job(contract_id, celery_task_id)`
  - `update_analysis_job(job_id, status, stage, attempts, timings, error=None)`
  - `get_active_analysis_job(contract_id)`
- Add structured JSON logging fields:
  - `contract_id`
  - `user_id`
  - `job_id`
  - `celery_task_id`
  - `stage`
  - `clause_index`
  - `contract_type`
  - `provider_used`
  - `retrieval_latency_ms`
  - `llm_latency_ms`
  - `retry_count`
  - `error_type`
  - `error_message`
- Measure and store timings in `analysis_jobs.timings`, including extraction, splitting, retrieval total, LLM total, saving, and total duration.
- Celery task retry policy:
  - Retry transient infrastructure/provider failures with exponential backoff.
  - Do not retry validation errors such as invalid PDF or no extractable text.
  - Clause-level LLM failures remain `analysis_status='failed'` and do not fail the whole contract unless every clause fails.

## Test Plan
- Backend unit tests:
  - Upload creates `uploaded` contract and stores PDF path without extracting.
  - Analyse endpoint enqueues Celery once and prevents duplicate active jobs.
  - Status endpoint returns exact stage/progress fields.
  - Worker updates statuses in the required order.
  - Worker records retrieval and LLM latency per clause.
  - Worker marks invalid PDFs as `failed` with useful `error_message`.
  - Existing failed-clause scoring behavior remains unchanged.
- Backend integration-style tests with mocked Redis/Celery/Supabase Storage:
  - Full pipeline success reaches `complete`.
  - Transient worker error triggers retry metadata.
  - All-clause LLM failure returns `Analysis Incomplete`, not a hidden medium-risk result.
- Frontend tests/build checks:
  - Dashboard maps backend statuses to progress labels.
  - Failed status displays backend error.
  - Results page is opened only after `has_results=true`.
- Verification commands:
  - `python3 -m compileall backend`
  - `python3 -m pytest backend/tests`
  - `npm run build`

## Assumptions
- Use Celery + Redis as the production queue stack.
- Use Supabase Storage as the production PDF storage backend.
- Keep the existing two-step frontend flow: upload first, then start analysis.
- Keep Supabase as the source of truth for job and contract status.
- Add local `DEV_MODE` fallbacks, but production correctness targets Supabase Storage + Redis + Celery.
- This phase adds structured logs and job metadata, but not full OpenTelemetry or hosted alerting yet.
