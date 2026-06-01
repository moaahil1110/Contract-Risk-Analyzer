# Priority 1 Production Hardening Plan

## Summary
Implement correctness, trust, and testability improvements so the app stops hiding failures, uses one backend source of truth, and produces defensible RAG-backed results. This phase will not build the full RAG evaluation harness yet, but it will add the schema and behavior needed for reliable scoring, failed-clause handling, type detection, and core automated tests.

## Key Changes

### Backend Truth And Scoring
- Make the backend the only authority for `health.score`, `health.grade`, and `health.label`.
- Extend clause results with:
  - `analysis_status`: `success`, `retried`, or `failed`
  - `retry_count`
  - `error_message`
  - `provider_used`
  - `retrieved_benchmarks`
- Failed clauses become:
  - `analysis_status: "failed"`
  - `risk_level: "unknown"`
  - `risk_score: null`
  - excluded from health score calculation
- Extend health output with:
  - `unknown_count`
  - `failed_clause_count`
  - `scored_clause_count`
  - existing `risk_counts` preserved for high/medium/low
- If every clause fails, return:
  - `score: 0`
  - `grade: "N/A"`
  - `label: "Analysis Incomplete"`

### Contract Type Handling
- Stop overwriting user-selected `contract_type`.
- Store:
  - `selected_contract_type`
  - `detected_contract_type`
  - `contract_type_confidence`
  - `contract_type` as the effective type for backward compatibility
- Detection should return type plus confidence.
- Effective type rule:
  - Use detected type if confidence is high enough.
  - Otherwise use selected type.
  - If selected and detected disagree, expose that conflict in API response.
- Use effective type for RAG retrieval and LLM prompts.

### RAG Reliability Foundation
- Update retrieval to accept `contract_type`.
- First retrieve benchmarks filtered by effective contract type.
- If too few filtered benchmarks are found, fall back to broader retrieval.
- Return benchmark metadata with each clause:
  - benchmark id
  - contract type
  - clause type
  - similarity score
  - risk notes
- Store this retrieval metadata with the clause analysis so bad outputs can be debugged later.

### Frontend And Export
- Update `HealthMeter` to accept backend `grade` and `label` instead of recalculating.
- Add UI handling for failed/unknown clauses:
  - show a visible “X clauses failed analysis” warning
  - show failed clauses separately or with an “Analysis Failed” badge
  - do not show failed clauses as medium risk
- Update `RiskBadge` to support `unknown`.
- Update PDF export to include:
  - backend grade/label
  - failed clause count
  - unknown clauses
  - retrieved benchmark references where available

### Database Migration
- Add a new migration after `001_initial_schema.sql`.
- `contracts` additions:
  - `selected_contract_type TEXT`
  - `detected_contract_type TEXT`
  - `contract_type_confidence NUMERIC`
  - `failed_clause_count INTEGER DEFAULT 0`
  - `scored_clause_count INTEGER DEFAULT 0`
  - `unknown_risk_count INTEGER DEFAULT 0`
- `clause_analyses` additions:
  - `analysis_status TEXT DEFAULT 'success'`
  - `retry_count INTEGER DEFAULT 0`
  - `error_message TEXT`
  - `provider_used TEXT`
  - `retrieved_benchmarks JSONB`
- Backfill existing rows:
  - `selected_contract_type = contract_type`
  - `detected_contract_type = contract_type`
  - `contract_type_confidence = 1.0`
  - existing clauses get `analysis_status = 'success'`

## Test Plan
- Add `pytest` to backend test dependencies.
- Add scorer tests:
  - high/medium/low scoring still matches blueprint
  - failed/unknown clauses are excluded from score
  - all-failed contract returns `Analysis Incomplete`
- Add contract type tests:
  - EC-style text detects `employment`
  - NDA-style text detects `nda`
  - low-confidence detection falls back to selected type
  - selected/detected conflict is exposed
- Add LLM failure tests:
  - provider failure returns `analysis_status: failed`
  - failed clauses do not become medium risk
  - retry metadata is preserved
- Add API tests with monkeypatched LLM/RAG:
  - upload preserves selected type
  - analyse stores detected/effective type
  - get analysis returns official backend grade/label
  - export includes failed clause count
- Run:
  - `python3 -m compileall backend`
  - backend pytest suite
  - `npm run build`

## Assumptions
- Failed clauses should be excluded from scoring and shown as `unknown`.
- Detected contract type should override selected type only when confidence is high.
- This phase adds core pytest coverage, not the full RAG evaluation harness.
- Existing Supabase data should remain readable after migration.
- Current `contract_type` remains in API responses as the effective type to avoid breaking frontend/history/export code.
