# E2M Backend

FastAPI service for the E2M exterior renovation planner. Owns projects, photo uploads, analysis
jobs and (in later phases) materials, quantities, costs and reports.

## How it talks to Supabase

The backend holds **no database password and no secret key**. For every request it calls
Supabase's Data API and Storage with:

- the project's **publishable key** (`apikey` header), and
- the **signed-in user's access token** (`Authorization: Bearer …`), forwarded from the frontend.

Supabase therefore runs each query *as that user*, and the Row Level Security policies in
[`supabase/schema.sql`](supabase/schema.sql) decide what they can see: their own projects, jobs,
regions and photos only. Background analysis jobs also run with the user's token.

## Phase 1 scope

- Supabase Auth: Bearer tokens verified against the project's JWKS.
- `POST /api/v1/projects`: upload a photo. It is EXIF-rotated and stripped of metadata (including
  GPS), downscaled to a ≤2048 px working copy plus thumbnail, and quality-checked. Unusable photos
  are rejected with `422` and a `quality_report` explaining how to retake them.
- Projects: list, open, rename, delete.
- Analysis jobs run in the background; poll `GET /api/v1/jobs/{id}` or the project.
- Photos live in the private `project-images` bucket; the API returns short-lived signed URLs.

## Setup

### 1. Create the database schema (once)

Open Supabase Dashboard → **SQL Editor** → **New query**, paste the whole of
[`supabase/schema.sql`](supabase/schema.sql), and click **Run**. It creates the tables, Row Level
Security policies, the private `project-images` bucket and its storage policies. It is safe to run
again after changes.

Then run [`supabase/seed_materials.sql`](supabase/seed_materials.sql) to load the material catalog
(safe to re-run; it updates rates in place).

**Already ran an earlier `schema.sql`?** Run the files in `supabase/migrations/` you have not run
yet, in order (`002_photos.sql` … `005_estimate.sql`), then `seed_materials.sql`.

### Material catalog

The catalog lives in [`app/catalog.py`](app/catalog.py): 14 materials (paints, texture, plaster,
stone, tiles, ACP/HPL panels, MS/SS/glass railings) with material and labour rates, coverage or unit
size, wastage, the parts of the house each suits, and suitability / maintenance / durability notes.
Rates are **indicative**: three follow CPWD DSR 2021 items (13.46.1, 13.45.1, 13.1), the rest are
market estimates — check them against the current DSR or local quotes. After editing the catalog,
regenerate the SQL with `python -m scripts.generate_seed_sql` and run it in the SQL Editor.

### 2. Install and configure

```bash
cd E2M_backend
uv venv --python 3.12 .venv          # or: python3.12 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp config.example.json config.json
```

All settings live in `config.json` (gitignored; `config.example.json` is the template):

| Key | Purpose |
|-----|---------|
| `supabase.url` | `https://<project-ref>.supabase.co` |
| `supabase.publishable_key` | Dashboard → Project Settings → **API Keys** → publishable key (`sb_publishable_…`) |
| `supabase.storage_bucket` | Photo bucket created by `schema.sql` (`project-images`) |
| `ai_geometry.url` | Base URL of the E2M_ai-geometry service (the Kaggle tunnel URL when running there) |
| `ai_geometry.api_key` | Must match `auth.api_key` of the AI service (printed by the Kaggle notebook) |
| `app.cors_origins` | Frontend origins allowed to call the API |
| `storage.backend` | `supabase`, or `local` for offline development |
| `auth.disabled` | `true` only for offline development (fixed dev user) |
| `pricing.*` | Labour cess, GST and default wastage used by the cost engine |

`E2M_CONFIG_FILE` selects another file (e.g. `config.staging.json`). Any single value can be
overridden by an environment variable `E2M_<SECTION>__<KEY>`, e.g. `E2M_AI_GEOMETRY__URL`;
precedence is environment > config.json > defaults.

### 3. Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Missing or placeholder settings are reported in plain language at startup. If the tables have not
been created yet, the API answers with "Run supabase/schema.sql in the Supabase SQL Editor".

### Offline development

No Supabase at all: data is kept in memory (lost on restart), photos on disk, and a fixed dev
user. Create `config.local.json`:

```json
{
  "storage": { "backend": "local" },
  "auth": { "disabled": true }
}
```

```bash
E2M_CONFIG_FILE=config.local.json .venv/bin/uvicorn app.main:app --reload --port 8000
```

Pair it with the frontend running `VITE_AUTH_DISABLED=true`.

## Changing the schema

Update `supabase/schema.sql` (the full schema for fresh setups) **and** add a numbered upgrade
file under `supabase/migrations/` for existing databases; run the upgrade in the SQL Editor.

## Tests

```bash
.venv/bin/python -m pytest
```

Tests use the in-memory repository and local storage, plus mocked HTTP for the Supabase
request layer, so they run offline.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health`, `/api/v1/health` | Liveness |
| POST | `/api/v1/projects` | Create a project from 1–8 photos (multipart `images`, matching `elevations`, optional `name`); analyses each |
| POST | `/api/v1/projects/{id}/photos` | Add more photos (same fields) |
| GET | `/api/v1/projects` | List my projects (cover photo, photo and region counts, status) |
| GET | `/api/v1/projects/{id}` | Project, photos (signed URLs, latest job, regions) and whole-house totals |
| PATCH | `/api/v1/projects/{id}` | Rename |
| DELETE | `/api/v1/projects/{id}` | Delete project and all its photos |
| PATCH | `/api/v1/photos/{id}` | Change side (`elevation`) or make it the counted photo (`is_primary: true`) |
| DELETE | `/api/v1/photos/{id}` | Remove a photo (409 for the last one) |
| POST | `/api/v1/photos/{id}/analyze` | Re-run analysis for a photo (409 if one is running) |
| POST | `/api/v1/photos/{id}/confirm` | Mark the photo's regions as reviewed |
| PUT | `/api/v1/photos/{id}/reference` | Your measurement of one region (`segment_id`, `dimension`: height/width, `metres`) — rescales the photo |
| DELETE | `/api/v1/photos/{id}/reference` | Remove your measurement |
| PATCH | `/api/v1/segments/{id}` | Change what a region is (`label`) |
| PUT | `/api/v1/segments/{id}/size` | Exact size you measured: `{width_m, height_m}` or `{area_sqm}` (surfaces), `{length_m}` (railings, roof edges) |
| DELETE | `/api/v1/segments/{id}/size` | Go back to the estimated size |
| DELETE | `/api/v1/segments/{id}` | Delete a wrong region |
| GET | `/api/v1/materials` | Material catalog |
| POST | `/api/v1/projects/{id}/variants` | New design (`name`, optional `copy_from` to duplicate) |
| PATCH / DELETE | `/api/v1/variants/{id}` | Rename / delete a design |
| PUT | `/api/v1/variants/{id}/assignments` | Apply a material (and paint colour) to regions: `segment_ids`, `material_id`, `color` |
| DELETE | `/api/v1/variants/{id}/assignments?segment_ids=…` | Remove the material from regions |
| GET | `/api/v1/projects/{id}/estimate` | Quantities and cost for every design |
| PUT / DELETE | `/api/v1/projects/{id}/rates/{material_id}` | Set (`material_rate`, `labor_rate`) / reset this project's rate for a material |
| PATCH | `/api/v1/projects/{id}/estimate-settings` | `{"include_gst": true/false}` |
| GET | `/api/v1/jobs/{id}` | Job status and progress |

**How sizes are measured** (`app/services/measurement.py`): sizes are recomputed from each
region's outline on every read, using one scale per photo, best source first — your measurement →
standard door height 2.1 m (else window height 1.2 m) → depth model distance ÷ focal length →
assumed 10 m distance (flagged). A region you measured exactly uses your size instead.
Walls are reported net of the windows and doors inside them.
Surfaces are treated as facing the camera, so photos taken at an angle under-estimate area.

**How the estimate is calculated** (`app/services/estimate.py`), per design and material:
quantity = measured size × (1 + wastage); material cost = quantity × material rate; labour cost =
measured size × labour rate (no labour on offcuts). Purchase quantities: paint litres and cans
(+ primer at 0.09 L/m²), cement-paint bags, tile/slab and sheet counts. Category totals, subtotal,
optional GST (`pricing.gst_rate`, 18%), grand total. Only counted photos are included; regions
without a material are reported. Rates come from the catalog unless changed for the project.

**Photos and totals:** each photo shows one side of the house (front, left, right, rear, other).
Each side has exactly one *counted* (primary) photo; whole-house totals add up the counted photos
only, so two photos of the same wall are never added together. If a whole upload contains an
unusable photo, nothing is saved and the `422` response lists each problem photo with guidance.
