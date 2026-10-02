-- ════════════════════════════════════════════════════════════════════════════
-- E2M — migration 003: per-photo measurement settings.
--
-- Run once in Supabase Dashboard → SQL Editor if you created the database before this
-- change. Fresh setups only need supabase/schema.sql, which already includes it.
--
-- photos.measurement holds the camera focal length found by the AI service and the
-- user's own reference measurement, e.g.
--   {"focal_length_px": 1480.2, "focal_source": "model",
--    "reference": {"segment_id": "…", "dimension": "height", "metres": 2.1}}
-- ════════════════════════════════════════════════════════════════════════════

alter table public.photos add column if not exists measurement jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
