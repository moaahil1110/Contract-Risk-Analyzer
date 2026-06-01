-- Production hardening metadata for contract type detection and clause analysis status.

ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS selected_contract_type TEXT,
    ADD COLUMN IF NOT EXISTS detected_contract_type TEXT,
    ADD COLUMN IF NOT EXISTS contract_type_confidence NUMERIC,
    ADD COLUMN IF NOT EXISTS failed_clause_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scored_clause_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS unknown_risk_count INTEGER DEFAULT 0;

ALTER TABLE clause_analyses
    ADD COLUMN IF NOT EXISTS analysis_status TEXT DEFAULT 'success',
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS provider_used TEXT,
    ADD COLUMN IF NOT EXISTS retrieved_benchmarks JSONB;

UPDATE contracts
SET
    selected_contract_type = COALESCE(selected_contract_type, contract_type),
    detected_contract_type = COALESCE(detected_contract_type, contract_type),
    contract_type_confidence = COALESCE(contract_type_confidence, 1.0),
    failed_clause_count = COALESCE(failed_clause_count, 0),
    scored_clause_count = COALESCE(scored_clause_count, total_clauses, 0),
    unknown_risk_count = COALESCE(unknown_risk_count, 0);

UPDATE clause_analyses
SET
    analysis_status = COALESCE(analysis_status, 'success'),
    retry_count = COALESCE(retry_count, 0),
    retrieved_benchmarks = COALESCE(retrieved_benchmarks, '[]'::jsonb);

CREATE INDEX IF NOT EXISTS idx_clauses_analysis_status ON clause_analyses(analysis_status);
