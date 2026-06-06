# Contract Risk Analyzer

Contract Risk Analyzer is a FastAPI and React application for uploading contract PDFs, extracting clauses, retrieving similar benchmark clauses with RAG, analyzing risk with an LLM provider chain, and exporting a PDF report.

## RAG Quality

The retrieval layer uses a curated benchmark library with 90 benchmark clauses:

- 30 NDA clauses
- 30 employment clauses
- 30 vendor/MSA clauses
- Each contract type has 10 low-risk, 10 medium-risk, and 10 high-risk examples

Every benchmark includes structured metadata: benchmark ID, contract type, clause type, risk level, risk rule, why the clause is risky, safer version, source metadata, jurisdiction, and tags. The ChromaDB store embeds richer benchmark text that includes the clause, risk rule, rationale, safer rewrite, and tags.

Clause analysis now returns RAG traceability fields:

- `cited_benchmark_ids`
- `risk_rule_applied`
- `evidence_summary`
- `benchmark_alignment`
- `retrieved_benchmarks`

This makes the result auditable: the frontend and PDF report show which benchmark evidence supported the risk decision.

## RAG Evaluation

Run the offline benchmark validation and retrieval quality checks:

```bash
python3 backend/scripts/build_benchmarks.py --force
python3 backend/scripts/run_rag_eval.py
```

The eval checks:

- benchmark schema validity
- metadata completeness
- top-3 retrieval hit rate
- contract-type precision
- analyzer JSON schema validity
- failed analysis rate

Current gates:

- top-3 retrieval hit rate must be at least 80%
- contract-type precision must be at least 90%
- metadata completeness must be 100%
- analyzer JSON/schema validity must be 100%

## Local Verification

```bash
python3 -m compileall backend
python3 -m pytest backend/tests
EMBEDDING_OFFLINE=true python3 backend/scripts/run_rag_eval.py
cd frontend
npm run build
```

## Background Jobs

Production analysis runs through Celery + Redis:

```bash
cd backend
uvicorn main:app --reload
celery -A worker.celery_app worker --loglevel=INFO
celery -A worker.celery_app flower --port=5555
```

For local development, use the one-command starter from the repository root:

```bash
./scripts/start_dev.sh
```

It checks Redis, starts the FastAPI backend, starts the Celery worker, starts the Vite frontend, and cleans up those processes when you press Ctrl-C.

Set `REDIS_URL`, `CELERY_RESULT_BACKEND`, `SUPABASE_STORAGE_BUCKET`, and Supabase credentials before running the worker in production. Uploaded PDFs are stored in Supabase Storage bucket `contracts`; `DEV_MODE=true` falls back to local `backend/uploads`.

Worker pool selection is configured by the app so the command stays the same across environments:

- `DEV_MODE=true` defaults to `CELERY_WORKER_POOL=solo` and `CELERY_WORKER_CONCURRENCY=1`. This avoids macOS `prefork` crashes with PyTorch/Chroma/sentence-transformers.
- `DEV_MODE=false` defaults to `CELERY_WORKER_POOL=prefork` with production concurrency from `CELERY_WORKER_CONCURRENCY` or `WEB_CONCURRENCY`.
- Unexpected worker task failures are persisted back to Supabase as failed jobs/contracts, so the frontend does not poll stale progress forever.

## PDF Export Dependencies

Polished PDF reports use WeasyPrint. It is preinstalled in the Docker image. For local macOS development, install the system libraries first:

```bash
brew install pango cairo gdk-pixbuf libffi
```

In production, WeasyPrint is required. If it is unavailable, `/export/{contract_id}` returns `503` instead of silently generating a lower-quality fallback report. In `DEV_MODE=true`, the backend may use a local fallback renderer for debugging. The `/health/details` endpoint reports whether WeasyPrint is usable.

## Deployment Checklist

Apply Supabase migrations in order:

```text
backend/db/migrations/001_initial_schema.sql
backend/db/migrations/002_production_hardening_metadata.sql
backend/db/migrations/003_rag_evidence_metadata.sql
backend/db/migrations/004_background_jobs_and_progress.sql
backend/db/migrations/005_security_auth_policies.sql
backend/db/migrations/006_product_polish_contract_lifecycle.sql
backend/db/migrations/007_rag_precision_metadata.sql
backend/db/migrations/008_clause_hierarchy_metadata.sql
```

Create a private Supabase Storage bucket named `contracts`.

Backend production env:

```text
DEV_MODE=false
ALLOWED_ORIGINS=https://<your-vercel-domain>
SUPABASE_URL=<project-url>
SUPABASE_SERVICE_KEY=<server-only-secret-key>
SUPABASE_STORAGE_BUCKET=contracts
REDIS_URL=<redis-url>
CELERY_RESULT_BACKEND=<redis-url>
EMBEDDING_OFFLINE=true
EMBEDDING_MODEL_PATH=/app/models/all-MiniLM-L6-v2
GROQ_API_KEY=<provider-key>
OPENROUTER_API_KEY=<provider-key>
OPENCODE_GO_API_KEY=<provider-key>
OPENCODE_GO_BASE_URL=https://opencode.ai/zen/go/v1
OPENCODE_GO_MODEL=deepseek-v4-flash
LLM_PROVIDER_ORDER=groq,opencode_go
BUILD_BENCHMARKS_ON_START=true
ANALYSIS_ACTIVE_JOB_TIMEOUT_MINUTES=30
```

Railway should run two services from the same GitHub repo plus one Redis service:

- Web service: root directory can stay as the repository root, Dockerfile path `backend/Dockerfile`, default start command from the Docker image. Set `RUN_WORKER_IN_WEB=false` after the worker service is online.
- Worker service: same repo and Dockerfile, same env vars, plus `PROCESS_TYPE=worker`.
- Redis service: connect its private Redis URL to both `REDIS_URL` and `CELERY_RESULT_BACKEND` on the web and worker services.

For very small demos, `RUN_WORKER_IN_WEB=true` can process jobs from the web service, but production-like Railway deployments should use the dedicated worker service so web restarts do not leave analyses queued.

Frontend production env:

```text
VITE_API_URL=https://<railway-backend-domain>
VITE_SUPABASE_URL=<project-url>
VITE_SUPABASE_ANON_KEY=<publishable-or-anon-key>
```

Railway commands if you are not using the Docker image entrypoint:

```bash
# Web service
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

# Worker service
celery -A worker.celery_app worker --loglevel=INFO
```

Vercel command:

```bash
cd frontend && npm ci && npm run build
```

Production smoke checks:

```bash
curl https://<backend-domain>/health
curl https://<backend-domain>/health/details
```

## Operations

Inspect stale jobs:

```bash
cd backend
python scripts/inspect_jobs.py 30
```

Mark stale jobs failed:

```bash
cd backend
python scripts/fail_stale_jobs.py 30
```

Clean up storage files for soft-deleted contracts older than 30 days:

```bash
cd backend
python scripts/cleanup_deleted_storage.py 30
```

Run authenticated browser E2E tests when local services are running:

```bash
cd frontend
E2E_EMAIL=<email> E2E_PASSWORD=<password> E2E_PDF_PATH=../NDA.pdf npm run test:e2e
```
