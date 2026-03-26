-- migrations/001_user_profiles.sql
-- Profile persistence table — Issue #39
-- Run in Supabase SQL editor or via psql.

CREATE TABLE IF NOT EXISTS user_profiles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL UNIQUE,          -- Clerk user_id (sub claim)
    profile_json JSONB NOT NULL,               -- serialized Profile dict
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for fast user_id lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles (user_id);

-- Row-level security: each user can only read/write their own row
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS (used by the backend service key)
-- Regular authenticated users are restricted to their own row
CREATE POLICY "Users can read own profile"
    ON user_profiles FOR SELECT
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users can upsert own profile"
    ON user_profiles FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users can delete own profile"
    ON user_profiles FOR DELETE
    USING (auth.uid()::text = user_id);
