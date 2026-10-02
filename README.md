# E2M Backend

FastAPI foundation for the E2M exterior renovation platform.

## Phase 1 scope

- FastAPI application with versioned health routes and CORS configuration.
- PostgreSQL-ready asynchronous SQLAlchemy session management.
- SQLAlchemy models and a baseline Alembic migration for projects, segments,
  materials, and BoQ items.
- Environment templates and a health-check test.

Feature routes for image processing, material selection, cost calculation, and
reports are intentionally deferred to their planned phases.

## Run locally

```bash
cd E2M_backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The service exposes `GET /health` and `GET /api/v1/health`.
