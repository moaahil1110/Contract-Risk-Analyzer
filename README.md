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
