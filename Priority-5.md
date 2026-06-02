# Priority 5 Product Polish Plan

## Summary

Turn the working Contract Risk Analyzer into a portfolio-ready product surface: clearer results, better failed-clause handling, polished downloadable reports, and a useful dashboard/history workflow. The implementation should create a repo plan file named `Priority-5.md`, then implement the changes below without changing the core RAG/scoring pipeline behavior.

## Key Changes

### Results UI

- Redesign the results page around clear product sections:
  - `Overall Score`: backend `health.score`, `health.grade`, and `health.label` only.
  - `Risk Breakdown`: high, medium, low, unknown, failed, scored counts.
  - `Top Risky Clauses`: top 5 high/medium clauses sorted by severity and `risk_score`.
  - `Failed Analysis`: separate section for failed clauses, never mixed into medium risk.
  - `Full Clause Analysis`: searchable/filterable clause list.
- Refine `HealthMeter` into a stable, clean gauge with no overlapping text and explicit labels: score, grade, risk label.
- Improve `ClauseCard`:
  - Show risk level, analysis status, provider, retry count, and RAG alignment as header chips.
  - Keep original text, plain-English explanation, risk reason, suggested fix, and RAG evidence in clear sub-sections.
  - Show retrieved benchmark IDs and similarity in a compact evidence panel.
- Add results filters for `all`, `high`, `medium`, `low`, `unknown`, `failed`, plus text search by clause title/body.

### Dashboard And History Polish

- Add history search/filter UI:
  - Search by filename.
  - Filter by status, contract type, and backend grade.
  - Show status badges for uploaded, queued, extracting, retrieving, analysing, saving, complete, and failed.
- Add row actions:
  - `View Results` for complete analyses.
  - `Download Report` for complete analyses using existing export endpoint.
  - `Re-run Analysis` for failed and complete contracts.
  - `Delete` using soft delete.
- Add confirmation dialogs for destructive or expensive actions:
  - Soft delete confirmation.
  - Rerun confirmation explaining old clause results will be replaced.

### Backend API And Data Lifecycle

- Add migration `006_product_polish_contract_lifecycle.sql`:
  - `contracts.deleted_at TIMESTAMP`
  - `contracts.rerun_count INTEGER DEFAULT 0`
  - `contracts.last_rerun_at TIMESTAMP`
  - Index for user history lookup excluding deleted rows.
- Update contract lookup helpers so deleted contracts are hidden from history, results, analysis, status, export, and rerun.
- Extend `GET /api/v1/history` with optional query params:
  - `search`
  - `status`
  - `contract_type`
  - `grade`
  - existing `limit` and `offset`
- Add `DELETE /api/v1/history/{contract_id}`:
  - Requires auth and ownership.
  - Soft-deletes by setting `deleted_at`.
  - Returns `204`.
  - Returns `409` if the contract has an active queued/running/retrying job.
- Add `POST /api/v1/analyse/{contract_id}/rerun`:
  - Requires auth and ownership.
  - Allowed only for `complete` and `failed`.
  - Clears old clause analyses and summary fields.
  - Resets status to `queued`, increments `rerun_count`, sets `last_rerun_at`, and enqueues a fresh Celery job using the existing stored PDF.
  - Returns the same queue metadata shape as `POST /analyse/{contract_id}`.

### Polished PDF Export

- Replace the manual text-PDF builder with WeasyPrint HTML/CSS rendering.
- Report structure:
  - Cover summary with filename, contract type, generated timestamp, score, grade, label.
  - Risk breakdown table/cards.
  - Deterministic recommendations based on risk counts, failed counts, score, contract type conflict, and top risky clauses.
  - Top risky clauses.
  - Failed/unknown clauses section.
  - Full clause analysis with plain-English explanation, risk reason, suggested fix, and RAG evidence.
  - Page numbers and consistent typography.
- Do not call an LLM during export. Recommendations are deterministic so export stays fast and reliable.

## Test Plan

- Backend pytest:
  - History filters return only owner-scoped, non-deleted contracts.
  - Soft delete hides a contract from history/results/export and blocks active-job deletion with `409`.
  - Rerun is allowed for failed/complete contracts, blocked for active contracts, clears old clause analyses, resets summary fields, and enqueues once.
  - Export HTML includes cover summary, risk breakdown, recommendations, failed count, top risky clauses, and benchmark evidence.
  - Export route still requires auth and ownership.
- Frontend verification:
  - `npm run build`
  - Results page shows backend grade/label without recalculating.
  - Failed clauses appear separately and not as medium risk.
  - Dashboard search/filter/status badges/actions render correctly.
  - Download report works from both results and history.
  - Delete and rerun confirmations behave correctly.
- Full verification:
  - `python3 -m compileall backend`
  - `python3 -m pytest backend/tests`
  - `cd frontend && npm run build`
  - Browser smoke test: upload/analyse, open results, export PDF, rerun a completed analysis, delete a history item.

## Assumptions

- Delete is soft delete by default.
- Rerun is available for failed and completed analyses only.
- Export recommendations are deterministic, not LLM-generated.
- Existing RAG retrieval, scoring, auth, ownership, Celery, and Supabase Storage behavior should remain unchanged.
- The official backend health score, grade, and label remain the only source of truth.
