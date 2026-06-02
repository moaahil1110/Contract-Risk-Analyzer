-- Priority 4: Security and auth hardening
-- Enable RLS on analysis_jobs, add owner-based policies, and add performance index.

-- Enable Row Level Security on analysis_jobs
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;

-- Owner-based SELECT policy on analysis_jobs through contracts.user_id
CREATE POLICY "Users can view analysis jobs of own contracts"
    ON analysis_jobs FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM contracts
        WHERE contracts.id = analysis_jobs.contract_id
        AND contracts.user_id = auth.uid()
    ));

-- Add composite index for fast owner-scoped contract lookups
CREATE INDEX IF NOT EXISTS idx_contracts_id_user ON contracts(id, user_id);
