-- migrations/002_usage_and_billing.sql
-- Usage metering table and billing columns for subscription tier support.
-- Run after 001_user_profiles.sql.

-- usage table for metering (tracks monthly tailor count per user)
CREATE TABLE IF NOT EXISTS usage (
    user_id TEXT NOT NULL,
    month TEXT NOT NULL,           -- format: "2026-03"
    resume_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, month)
);

-- Add plan + stripe columns to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
