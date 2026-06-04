-- Priority: RAG precision metadata for clause-type-aware retrieval.

ALTER TABLE clause_analyses
ADD COLUMN IF NOT EXISTS predicted_clause_type TEXT,
ADD COLUMN IF NOT EXISTS clause_type_confidence NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS clause_type_matched_terms JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS retrieval_quality TEXT DEFAULT 'none',
ADD COLUMN IF NOT EXISTS eligible_benchmark_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS citation_suppressed BOOLEAN DEFAULT false;

UPDATE clause_analyses
SET
  clause_type_confidence = COALESCE(clause_type_confidence, 0),
  clause_type_matched_terms = COALESCE(clause_type_matched_terms, '[]'::jsonb),
  retrieval_quality = COALESCE(retrieval_quality, 'none'),
  eligible_benchmark_count = COALESCE(eligible_benchmark_count, 0),
  citation_suppressed = COALESCE(citation_suppressed, false)
WHERE clause_type_confidence IS NULL
   OR clause_type_matched_terms IS NULL
   OR retrieval_quality IS NULL
   OR eligible_benchmark_count IS NULL
   OR citation_suppressed IS NULL;
