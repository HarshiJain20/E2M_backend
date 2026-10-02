-- ════════════════════════════════════════════════════════════════════════════
-- E2M Renovate — Supabase schema
--
-- Run once in Supabase Dashboard → SQL Editor → New query → paste → Run.
-- Safe to re-run: tables are created only if missing; policies and triggers are replaced.
--
-- Security model: the backend calls Supabase with the publishable key plus the signed-in
-- user's access token. Every table has Row Level Security, so each request only sees
-- rows belonging to that user. The anon role (publishable key without a user) gets nothing.
-- ════════════════════════════════════════════════════════════════════════════


-- ── Tables ───────────────────────────────────────────────────────────────────

create table if not exists public.projects (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name       text not null check (char_length(name) between 1 and 120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_user_id_idx on public.projects (user_id, updated_at desc);

-- One photo = one view of the house. Only the primary photo of each elevation counts toward totals.
create table if not exists public.photos (
  id                  uuid primary key default gen_random_uuid(),
  project_id          uuid not null references public.projects (id) on delete cascade,
  elevation           text not null default 'front'
                        check (elevation in ('front', 'left', 'right', 'rear', 'other')),
  is_primary          boolean not null default false,
  status              text not null default 'uploaded'
                        check (status in ('uploaded', 'processing', 'review', 'failed')),
  original_image_path text not null,
  working_image_path  text not null,
  thumbnail_path      text not null,
  image_width         integer not null check (image_width > 0),
  image_height        integer not null check (image_height > 0),
  image_meta          jsonb not null default '{}'::jsonb,
  quality_report      jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now()
);
create index if not exists photos_project_id_idx on public.photos (project_id, created_at);
create unique index if not exists photos_one_primary_per_elevation
  on public.photos (project_id, elevation) where is_primary;

create table if not exists public.jobs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references public.projects (id) on delete cascade,
  photo_id    uuid not null references public.photos (id) on delete cascade,
  kind        text not null default 'analyze',
  status      text not null default 'queued'
                check (status in ('queued', 'running', 'succeeded', 'failed')),
  stage       text,
  progress    integer not null default 0 check (progress between 0 and 100),
  error       text,
  result_meta jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz
);
create index if not exists jobs_project_id_idx on public.jobs (project_id, created_at desc);
create index if not exists jobs_photo_id_idx on public.jobs (photo_id, created_at desc);

create table if not exists public.segments (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  photo_id       uuid not null references public.photos (id) on delete cascade,
  label          text not null,
  source         text not null default 'auto' check (source in ('auto', 'user')),
  confidence     double precision,
  polygon        jsonb not null default '[]'::jsonb,   -- [[x, y], ...] normalised 0-1
  bbox           jsonb not null default '[]'::jsonb,   -- [x0, y0, x1, y1] normalised 0-1
  measure_type   text not null default 'area' check (measure_type in ('area', 'length')),
  area_sqm       double precision,
  length_m       double precision,
  scale_source   text,
  user_dimension jsonb,
  depth_stats    jsonb,
  is_confirmed   boolean not null default false,
  created_at     timestamptz not null default now()
);
create index if not exists segments_project_id_idx on public.segments (project_id);
create index if not exists segments_photo_id_idx on public.segments (photo_id);

-- Shared catalog: readable by every signed-in user, edited by admins in the dashboard.
create table if not exists public.materials (
  id             uuid primary key default gen_random_uuid(),
  sor_code       text,
  name           text not null,
  category       text not null,
  description    text,
  unit           text not null check (unit in ('sqm', 'rmt')),
  material_rate  double precision not null check (material_rate >= 0),
  labor_rate     double precision not null check (labor_rate >= 0),
  wastage_factor double precision not null default 0.10,
  coverage       jsonb,
  unit_size      jsonb,
  suitability    text,
  maintenance    text,
  durability     text,
  texture_ref    text,
  render_prompt  text,
  is_active      boolean not null default true
);

create table if not exists public.design_variants (
  id                  uuid primary key default gen_random_uuid(),
  project_id          uuid not null references public.projects (id) on delete cascade,
  name                text not null check (char_length(name) between 1 and 80),
  rendered_image_path text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists design_variants_project_id_idx on public.design_variants (project_id);

create table if not exists public.segment_materials (
  id          uuid primary key default gen_random_uuid(),
  variant_id  uuid not null references public.design_variants (id) on delete cascade,
  segment_id  uuid not null references public.segments (id) on delete cascade,
  material_id uuid not null references public.materials (id),
  unique (variant_id, segment_id)
);

create table if not exists public.project_rate_overrides (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references public.projects (id) on delete cascade,
  material_id   uuid not null references public.materials (id),
  material_rate double precision check (material_rate >= 0),
  labor_rate    double precision check (labor_rate >= 0),
  unique (project_id, material_id)
);

create table if not exists public.boq_items (
  id             uuid primary key default gen_random_uuid(),
  variant_id     uuid not null references public.design_variants (id) on delete cascade,
  segment_id     uuid references public.segments (id) on delete set null,
  category       text not null,
  material_id    uuid references public.materials (id),
  material_name  text not null,
  sor_code       text,
  measured_qty   double precision not null,
  wastage_factor double precision not null,
  quantity       double precision not null,
  quantity_unit  text not null,
  purchase_qty   jsonb,
  material_rate  double precision not null,
  labor_rate     double precision not null,
  material_cost  double precision not null,
  labor_cost     double precision not null,
  total_cost     double precision not null
);
create index if not exists boq_items_variant_id_idx on public.boq_items (variant_id);


-- ── updated_at maintenance ──────────────────────────────────────────────────

create or replace function public.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at before update on public.projects
  for each row execute function public.set_updated_at();

drop trigger if exists design_variants_set_updated_at on public.design_variants;
create trigger design_variants_set_updated_at before update on public.design_variants
  for each row execute function public.set_updated_at();


-- ── Row Level Security ──────────────────────────────────────────────────────

alter table public.projects               enable row level security;
alter table public.photos                 enable row level security;
alter table public.jobs                   enable row level security;
alter table public.segments               enable row level security;
alter table public.materials              enable row level security;
alter table public.design_variants        enable row level security;
alter table public.segment_materials      enable row level security;
alter table public.project_rate_overrides enable row level security;
alter table public.boq_items              enable row level security;

-- Projects: owner only. user_id cannot be changed to someone else.
drop policy if exists "projects: owner access" on public.projects;
create policy "projects: owner access" on public.projects
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- Tables hanging off a project: allowed when the parent project is the user's.
drop policy if exists "photos: via own project" on public.photos;
create policy "photos: via own project" on public.photos
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

drop policy if exists "jobs: via own project" on public.jobs;
create policy "jobs: via own project" on public.jobs
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

drop policy if exists "segments: via own project" on public.segments;
create policy "segments: via own project" on public.segments
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

drop policy if exists "design_variants: via own project" on public.design_variants;
create policy "design_variants: via own project" on public.design_variants
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

drop policy if exists "project_rate_overrides: via own project" on public.project_rate_overrides;
create policy "project_rate_overrides: via own project" on public.project_rate_overrides
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

-- Tables hanging off a design variant.
drop policy if exists "segment_materials: via own variant" on public.segment_materials;
create policy "segment_materials: via own variant" on public.segment_materials
  for all to authenticated
  using (exists (
    select 1 from public.design_variants v join public.projects p on p.id = v.project_id
    where v.id = variant_id and p.user_id = (select auth.uid())))
  with check (exists (
    select 1 from public.design_variants v join public.projects p on p.id = v.project_id
    where v.id = variant_id and p.user_id = (select auth.uid())));

drop policy if exists "boq_items: via own variant" on public.boq_items;
create policy "boq_items: via own variant" on public.boq_items
  for all to authenticated
  using (exists (
    select 1 from public.design_variants v join public.projects p on p.id = v.project_id
    where v.id = variant_id and p.user_id = (select auth.uid())))
  with check (exists (
    select 1 from public.design_variants v join public.projects p on p.id = v.project_id
    where v.id = variant_id and p.user_id = (select auth.uid())));

-- Materials: read-only catalog for signed-in users.
drop policy if exists "materials: signed-in users read active" on public.materials;
create policy "materials: signed-in users read active" on public.materials
  for select to authenticated
  using (is_active);


-- ── Grants (Data API) ───────────────────────────────────────────────────────

revoke all on public.projects, public.photos, public.jobs, public.segments, public.materials,
  public.design_variants, public.segment_materials, public.project_rate_overrides,
  public.boq_items from anon;

grant select, insert, update, delete on public.projects, public.photos, public.jobs, public.segments,
  public.design_variants, public.segment_materials, public.project_rate_overrides,
  public.boq_items to authenticated;
grant select on public.materials to authenticated;


-- ── Storage: private bucket for project photos ─────────────────────────────
-- Objects are stored as <user_id>/<project_id>/<file>; users may only touch their own folder.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('project-images', 'project-images', false, 20971520,
        array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

drop policy if exists "project-images: read own" on storage.objects;
create policy "project-images: read own" on storage.objects
  for select to authenticated
  using (bucket_id = 'project-images' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "project-images: upload own" on storage.objects;
create policy "project-images: upload own" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'project-images' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "project-images: update own" on storage.objects;
create policy "project-images: update own" on storage.objects
  for update to authenticated
  using (bucket_id = 'project-images' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'project-images' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "project-images: delete own" on storage.objects;
create policy "project-images: delete own" on storage.objects
  for delete to authenticated
  using (bucket_id = 'project-images' and (storage.foldername(name))[1] = (select auth.uid())::text);


-- Make the new tables visible to the Data API immediately.
notify pgrst, 'reload schema';
