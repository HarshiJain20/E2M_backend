-- ════════════════════════════════════════════════════════════════════════════
-- E2M — migration 004: material catalog details and paint colours.
--
-- Run once in Supabase Dashboard → SQL Editor if you created the database before this
-- change, then run supabase/seed_materials.sql to load the catalog.
-- Fresh setups: schema.sql already includes this; just run seed_materials.sql after it.
-- ════════════════════════════════════════════════════════════════════════════

alter table public.materials
  add column if not exists rate_source text,                               -- e.g. "CPWD DSR-based (indicative)"
  add column if not exists applies_to text[] not null default '{}'::text[], -- labels it can be applied to
  add column if not exists colorable boolean not null default false,       -- user picks a colour (paints)
  add column if not exists swatch text;                                    -- default colour for previews

alter table public.segment_materials
  add column if not exists color text;                                     -- chosen colour, #rrggbb

-- Design names are unique within a project ("Design A", "Design B", …).
create unique index if not exists design_variants_project_name_idx on public.design_variants (project_id, name);

notify pgrst, 'reload schema';
