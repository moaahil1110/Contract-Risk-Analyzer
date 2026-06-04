-- Priority: hierarchy-aware clause parsing and count metadata.

ALTER TABLE contracts
ADD COLUMN IF NOT EXISTS top_level_clause_count INTEGER,
ADD COLUMN IF NOT EXISTS parsed_section_count INTEGER;

UPDATE contracts
SET
  top_level_clause_count = COALESCE(top_level_clause_count, total_clauses),
  parsed_section_count = COALESCE(parsed_section_count, total_clauses)
WHERE top_level_clause_count IS NULL
   OR parsed_section_count IS NULL;

ALTER TABLE clause_analyses
ADD COLUMN IF NOT EXISTS clause_number TEXT,
ADD COLUMN IF NOT EXISTS parent_clause_number TEXT,
ADD COLUMN IF NOT EXISTS clause_level INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS section_type TEXT DEFAULT 'clause',
ADD COLUMN IF NOT EXISTS is_scored BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS subclauses JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS parsed_section_count INTEGER DEFAULT 1;

UPDATE clause_analyses
SET
  clause_level = COALESCE(clause_level, 1),
  section_type = COALESCE(section_type, 'clause'),
  is_scored = COALESCE(is_scored, true),
  subclauses = COALESCE(subclauses, '[]'::jsonb),
  parsed_section_count = COALESCE(parsed_section_count, 1)
WHERE clause_level IS NULL
   OR section_type IS NULL
   OR is_scored IS NULL
   OR subclauses IS NULL
   OR parsed_section_count IS NULL;

CREATE INDEX IF NOT EXISTS idx_clause_analyses_contract_clause_number
ON clause_analyses(contract_id, clause_number);
