-- ════════════════════════════════════════════════════════════════════════════
-- E2M — migration 002: several photos (views) per project.
--
-- For databases created with the first version of supabase/schema.sql. Run once in
-- Supabase Dashboard → SQL Editor. Existing projects keep their photo: it becomes the
-- project's primary "front" view, and its jobs and regions move with it.
-- Fresh setups only need supabase/schema.sql, which already includes this change.
-- ════════════════════════════════════════════════════════════════════════════

begin;

create table public.photos (
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
create index photos_project_id_idx on public.photos (project_id, created_at);
create unique index photos_one_primary_per_elevation
  on public.photos (project_id, elevation) where is_primary;

-- Each existing project's image becomes its primary front photo.
insert into public.photos (project_id, elevation, is_primary, status, original_image_path,
                           working_image_path, thumbnail_path, image_width, image_height,
                           image_meta, quality_report, created_at)
select id, 'front', true, status, original_image_path, working_image_path, thumbnail_path,
       image_width, image_height, image_meta, quality_report, created_at
from public.projects;

alter table public.jobs add column photo_id uuid references public.photos (id) on delete cascade;
update public.jobs j set photo_id = p.id from public.photos p where p.project_id = j.project_id;
alter table public.jobs alter column photo_id set not null;
create index jobs_photo_id_idx on public.jobs (photo_id, created_at desc);

alter table public.segments add column photo_id uuid references public.photos (id) on delete cascade;
update public.segments s set photo_id = p.id from public.photos p where p.project_id = s.project_id;
alter table public.segments alter column photo_id set not null;
create index segments_photo_id_idx on public.segments (photo_id);

alter table public.projects
  drop column status,
  drop column original_image_path,
  drop column working_image_path,
  drop column thumbnail_path,
  drop column image_width,
  drop column image_height,
  drop column image_meta,
  drop column quality_report;

alter table public.photos enable row level security;
create policy "photos: via own project" on public.photos
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));

revoke all on public.photos from anon;
grant select, insert, update, delete on public.photos to authenticated;

commit;

notify pgrst, 'reload schema';
