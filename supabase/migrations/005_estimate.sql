-- ════════════════════════════════════════════════════════════════════════════
-- E2M — migration 005: estimate settings per project.
--
-- Run once in Supabase Dashboard → SQL Editor if you created the database before this
-- change. Fresh setups only need supabase/schema.sql, which already includes it.
--
-- projects.estimate_settings, e.g. {"include_gst": true}
-- Per-project rate changes use the existing project_rate_overrides table.
-- ════════════════════════════════════════════════════════════════════════════

alter table public.projects add column if not exists estimate_settings jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
