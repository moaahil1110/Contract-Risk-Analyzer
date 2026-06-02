-- Priority 2: RAG evidence metadata for clause-level traceability.

ALTER TABLE clause_analyses
ADD COLUMN IF NOT EXISTS cited_benchmark_ids JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS risk_rule_applied TEXT,
ADD COLUMN IF NOT EXISTS evidence_summary TEXT,
ADD COLUMN IF NOT EXISTS benchmark_alignment TEXT DEFAULT 'none';

UPDATE clause_analyses
SET
  cited_benchmark_ids = COALESCE(cited_benchmark_ids, '[]'::jsonb),
  benchmark_alignment = COALESCE(benchmark_alignment, 'none')
WHERE cited_benchmark_ids IS NULL
   OR benchmark_alignment IS NULL;
