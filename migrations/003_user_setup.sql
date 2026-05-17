-- migrations/003_user_setup.sql
-- First-run setup wizard state — Epic #91 (M1).
-- Run in Supabase SQL editor or via psql.
-- Idempotent: safe to apply on databases where some columns already exist.

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS target_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS target_companies JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS setup_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS setup_skipped_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS setup_progress_step TEXT NOT NULL DEFAULT 'welcome';

-- Existing RLS policies from 001_user_profiles.sql apply at the row level
-- (auth.uid()::text = user_id) and cover all columns on the row.
-- No new policies needed.

-- Index supports the "skipped vs completed" route guard query:
CREATE INDEX IF NOT EXISTS idx_user_profiles_setup_state
    ON user_profiles (setup_completed_at, setup_skipped_at);
