-- Priority 3: background jobs, durable upload metadata, and progress tracking.

ALTER TABLE contracts
ADD COLUMN IF NOT EXISTS storage_path TEXT,
ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER,
ADD COLUMN IF NOT EXISTS mime_type TEXT,
ADD COLUMN IF NOT EXISTS progress_percent INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS status_message TEXT,
ADD COLUMN IF NOT EXISTS error_message TEXT,
ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;

UPDATE contracts
SET
  status = CASE WHEN status = 'processing' THEN 'queued' ELSE status END,
  progress_percent = COALESCE(progress_percent, CASE WHEN status = 'complete' THEN 100 ELSE 0 END),
  status_message = COALESCE(status_message, status)
WHERE progress_percent IS NULL
   OR status_message IS NULL
   OR status = 'processing';

CREATE TABLE IF NOT EXISTS analysis_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id UUID REFERENCES contracts(id) ON DELETE CASCADE,
  celery_task_id TEXT,
  status TEXT DEFAULT 'queued',
  current_stage TEXT,
  progress_percent INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  last_error TEXT,
  timings JSONB DEFAULT '{}'::jsonb,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT NOW(),
  started_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT NOW(),
  finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_contract ON analysis_jobs(contract_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_task_id ON analysis_jobs(celery_task_id);
