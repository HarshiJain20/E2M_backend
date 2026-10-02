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
| `ai_geometry.url` | Base URL of the E2M_ai-geometry service |
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

Edit `supabase/schema.sql` (keep it re-runnable: `create table if not exists`,
`drop policy if exists`) or add a new SQL file under `supabase/`, and run it in the SQL Editor.

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
| POST | `/api/v1/projects` | Upload photo (multipart `image`, optional `name`), start analysis |
| GET | `/api/v1/projects` | List my projects |
| GET | `/api/v1/projects/{id}` | Project, signed image URLs, latest job, segments |
| PATCH | `/api/v1/projects/{id}` | Rename |
| DELETE | `/api/v1/projects/{id}` | Delete project and its photos |
| POST | `/api/v1/projects/{id}/analyze` | Re-run analysis (409 if one is running) |
| GET | `/api/v1/jobs/{id}` | Job status and progress |
