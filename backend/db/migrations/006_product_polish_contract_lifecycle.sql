-- Priority 5: Product polish contract lifecycle
-- Adds soft delete, rerun tracking, and history index

ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS rerun_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_rerun_at TIMESTAMP WITH TIME ZONE;

-- Index for fast user history lookup excluding deleted rows
CREATE INDEX IF NOT EXISTS idx_contracts_user_not_deleted
    ON contracts (user_id, uploaded_at DESC)
    WHERE deleted_at IS NULL;
