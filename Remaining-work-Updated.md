# Fix Remaining E2E/Production Blockers — UPDATED 2026-06-03

## What was fixed today

1. **NDA detector / E2E assertions**
   - `detect_contract_type()` already correct; verified via unit tests.
   - E2E spec updated to assert `Type: nda` visibility and benchmark alignment on results page.

2. **Provider quota/backoff behavior**
   - Added circuit-breaker logic in `backend/pipeline/llm_analyser.py`.
   - Groq/OpenRouter catch `429`, parse `Retry-After` / `x-ratelimit-reset`, mark provider unavailable.
   - Env vars added: `LLM_PROVIDER_ORDER`, `LLM_PROVIDER_MAX_RETRIES`, `LLM_PROVIDER_COOLDOWN_SECONDS`, `LLM_REQUEST_DELAY_MS`.
   - Provider exhaustion adds contract-level `warning: "Provider quota exhausted; rerun later."` when >50% of clauses fail.
   - Tests: `tests/test_provider_circuit_breaker.py` (6 tests, all passing).

3. **Polished PDF export dependencies**
   - Dockerfile updated with WeasyPrint system packages.
   - `/health/details` now reports `weasyprint: {usable, pdf_bytes}`.
   - Added `tests/test_weasyprint_health.py` smoke test.
   - README documents macOS setup: `brew install pango cairo gdk-pixbuf libffi`.
   - CI workflow installs WeasyPrint deps.

4. **History search resilience**
   - `_sanitize_ilike_pattern()` escapes `%` and `_` before Supabase `ilike`.
   - `get_user_contracts()` retries once on transient Supabase failure.
   - Production returns `503`; dev falls back to in-memory.
   - Tests: `tests/test_history_search.py` (4 tests, all passing).

5. **Frontend build warning**
   - Removed dynamic `import('./supabase.js')` from `frontend/src/lib/api.js`.
   - Uses static `import { getSession } from './supabase.js'`.
   - `npm run build` now clean.

6. **CI-safe mocked E2E**
   - `E2E_MOCK_PROVIDER=true` backend mode returns deterministic fixture data without real LLM calls.
   - Frontend `VITE_CI_BYPASS_AUTH=true` skips login wall for CI.
   - GitHub Actions `e2e` job added to `.github/workflows/ci.yml`.
   - Real-provider E2E remains manual with credentials.

7. **Redis-backed rate limiting**
   - `core/rate_limit.py` now uses Redis sliding-window counters when `REDIS_URL` is configured.
   - Falls back to in-memory limiter on Redis connection failure.
   - Tests: `tests/test_rate_limit.py` (7 tests, all passing).

8. **Stale jobs**
   - Ran `python backend/scripts/fail_stale_jobs.py 30` locally.
   - README already documents scheduled command.

## Remaining (deployment/manual)

+ Production deployment to Railway/Vercel.
+ Run real browser E2E with paid provider quota (`./scripts/start_dev.sh` + `npm run test:e2e`).
+ Rotate any exposed API keys before public launch.

---

# Original Plan (kept for reference)

## Summary

The app’s main signed-in `NDA.pdf` flow works end to end, but it is not production-clean yet. The remaining fixes are mostly reliability hardening around contract-type verification, provider quotas, PDF rendering dependencies, history search resilience, and CI-safe E2E. The implementation order should be strict because some later checks depend on earlier fixes.

## Fix Order

1. **Confirm NDA detector fix with a fresh worker run**
   - Restart backend and Celery worker so the fixed `detect_contract_type()` code is loaded.
   - Re-upload `NDA.pdf` as NDA.
   - Verify API result has:
     - `selected_contract_type: "nda"`
     - `detected_contract_type: "nda"`
     - effective `contract_type: "nda"`
     - retrieved benchmark metadata uses NDA benchmarks.
   - Update the Playwright E2E test to assert contract type and benchmark type, not only page visibility.

2. **Fix provider quota/backoff behavior**
   - Add a provider circuit breaker in `backend/pipeline/llm_analyser.py`.
   - When Groq/OpenRouter/OpenCode Go returns `429`, parse `Retry-After` or provider reset metadata when available.
   - Mark that provider unavailable until the retry window expires instead of retrying it for every clause.
   - Add env config:
     - `LLM_PROVIDER_ORDER=groq,openrouter,opencode_go`
     - `LLM_PROVIDER_MAX_RETRIES=2`
     - `LLM_PROVIDER_COOLDOWN_SECONDS=60`
     - `LLM_REQUEST_DELAY_MS=250`
   - If provider exhaustion causes more than a configured threshold of failed clauses, keep clause failures visible and add a contract-level warning like "Provider quota exhausted; rerun later."
   - Tests:
     - provider `429` opens circuit.
     - next clause skips unavailable provider.
     - fallback does not silently become medium risk.
     - warning appears when many clauses fail.

3. **Fix polished PDF export dependencies**
   - Update `backend/Dockerfile` system packages for WeasyPrint:
     - `libcairo2`
     - `libpango-1.0-0`
     - `libpangocairo-1.0-0`
     - `libgdk-pixbuf-2.0-0`
     - `libffi-dev`
     - `shared-mime-info`
   - Keep fallback renderer, but make `/health/details` report whether WeasyPrint is usable.
   - Add a small export smoke test that imports WeasyPrint and renders a one-page PDF.
   - Document local macOS setup separately: `brew install pango cairo gdk-pixbuf libffi`.

4. **Harden history search**
   - Sanitize search input before passing to Supabase `ilike`.
   - Add one retry for transient Supabase `5xx`/Cloudflare failures.
   - In production, return `503` with a clear message after retry failure.
   - In dev, fallback to in-memory only after logging that Supabase failed.
   - Add tests:
     - search applies filename filter.
     - transient Supabase failure retries once.
     - production search failure returns `503`.

5. **Clean build warning from Supabase import**
   - Remove the dynamic Supabase import from `frontend/src/lib/api.js`.
   - Use the already shared static Supabase client import path consistently.
   - Verify `npm run build` no longer shows the dynamic/static import warning.

6. **Add CI-safe mocked E2E**
   - Add `E2E_MOCK_PROVIDER=true` backend mode.
   - In mock mode, return deterministic clause analysis from fixture data without external LLM calls.
   - Add GitHub Actions job that starts Redis, backend, Celery, frontend, then runs Playwright.
   - Keep real-provider E2E manual because provider quotas make it flaky.

7. **Add Redis-backed rate limiting**
   - Keep current in-memory limiter for dev/test fallback.
   - When `REDIS_URL` is configured, store counters in Redis with expiry.
   - Make limiter behavior identical for upload/analyse/rerun/export.
   - Add tests for Redis limiter and Redis-unavailable fallback.

8. **Clean stale jobs**
   - Run the existing stale-job script once locally to mark old queued jobs failed.
   - Add a documented scheduled command for production:
     - `python backend/scripts/fail_stale_jobs.py 30`
   - Confirm stale queued jobs no longer appear as active in history/rerun/delete flows.

## Acceptance Criteria

- Fresh `NDA.pdf` browser E2E passes with effective contract type `nda`.
- No analysis stage gets stuck.
- Rerun either completes cleanly with available provider quota or shows a clear provider-quota warning.
- WeasyPrint renders the polished PDF in Docker/production.
- History search does not silently mask production Supabase failures.
- Frontend build has no Supabase dynamic/static import warning.
- Backend tests pass.
- Frontend build passes.
- Playwright mocked E2E passes in CI.
- `remaining-stuff.md` is updated so only deployment/manual items remain.

## Verification Commands

```bash
python -m compileall backend
python -m pytest backend/tests
EMBEDDING_OFFLINE=true python backend/scripts/run_rag_eval.py
cd frontend && npm run build
cd frontend && npm run test:e2e
```

For the real local browser run:

```bash
./scripts/start_dev.sh
cd frontend
E2E_EMAIL=<email> E2E_PASSWORD=<password> E2E_PDF_PATH=../NDA.pdf npm run test:e2e
```

## Assumptions

- The existing detector fix stays; we only verify it with a restarted worker.
- We do not remove failed/unknown clause visibility. It is correct production behavior.
- Provider quota exhaustion is treated as an operational reliability problem, not a scoring bug.
- Production deployment remains Railway backend/worker, Redis, Vercel frontend, Supabase DB/storage/auth.
