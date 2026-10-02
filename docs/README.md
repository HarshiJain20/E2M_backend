# E2M — Documentation

AI-based exterior house renovation and cost estimation (prototype).

| Document | Covers (problem statement §9) |
|----------|-------------------------------|
| [Architecture](architecture.md) | 1. System architecture: components, data, models, deployment |
| [User workflow](workflow.md) | 2. User workflow, screen by screen |
| [How estimation works](estimation.md) | 4. Measurement, quantities and cost, with a worked example |
| [Limitations](limitations.md) | 4. What the prototype does not do and where it can be wrong |
| [Open-source components](open-source.md) | Models and libraries used, and their licences |

The prototype itself (§9.3) is the three repositories:

| Repository | Role |
|------------|------|
| `E2M_frontend` | React web app |
| `E2M_backend` | API: projects, photos, review, measurement, materials, estimate, redesign preview, PDF report (this repo) |
| `E2M_ai-geometry` | AI service: detection, depth, photorealistic rendering (runs on a GPU, e.g. a free Kaggle notebook) |

## Requirements coverage

| Requirement | Where |
|-------------|-------|
| 5.1 Image upload, several views, quality checks | Upload page; `app/services/images.py` |
| 5.2 Detect walls, windows, balconies, pillars, parapets, gates, roof edges; review and correct | AI service `services/segmentation`; Review page |
| 5.3 Material catalogue with suitability, maintenance, durability | `app/catalog.py`; Materials page |
| 5.4 Redesigned image, before/after | `app/services/render.py` (standard), AI service `services/render` (photorealistic) |
| 5.5 Surface area from reference sizes, perspective/depth, user measurements | `app/services/measurement.py`; AI service `services/depth`, `services/spatial_math` |
| 5.6 Quantities | `app/services/estimate.py` |
| 5.7 Costs with editable rates | `app/services/estimate.py`; Estimate page |
| 5.8 Report | `app/services/reports/pdf.py`; "Download PDF report" on the Estimate page |
| Save and re-edit projects; multiple users | Supabase Postgres with Row Level Security |
