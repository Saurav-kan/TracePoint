-- Migration: Update investigation_logs.effort_level to use actual effort levels
-- (standard, adversarial, deep, proof) instead of legacy low/medium/high.
--
-- Run this against an existing database:
--   psql $DATABASE_URL -f database/migrate_effort_levels.sql

-- 1. Widen column to fit "adversarial" (11 chars) and future values
ALTER TABLE investigation_logs
  ALTER COLUMN effort_level TYPE VARCHAR(20);

-- 2. Migrate legacy values to actual effort levels
UPDATE investigation_logs
SET effort_level = CASE effort_level
  WHEN 'low'    THEN 'standard'
  WHEN 'medium' THEN 'adversarial'
  WHEN 'high'   THEN 'deep'
  ELSE effort_level
END
WHERE effort_level IN ('low', 'medium', 'high');

-- 3. Set default for new rows
ALTER TABLE investigation_logs
  ALTER COLUMN effort_level SET DEFAULT 'standard';
