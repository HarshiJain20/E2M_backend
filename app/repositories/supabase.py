"""
Repository backed by Supabase's Data API (PostgREST).

Each request carries the publishable key (`apikey`) and the signed-in user's access token
(`Authorization`), so Postgres evaluates Row Level Security as that user.
"""
import httpx

from app.core.config import Settings
from app.repositories.base import RepositoryError

RETURN_ROWS = {"Prefer": "return=representation"}


class SupabaseRepository:
    def __init__(self, settings: Settings, access_token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._base = f"{settings.supabase.url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": settings.supabase.publishable_key,
            "Authorization": f"Bearer {access_token}",
        }
        self._timeout = settings.supabase.timeout_seconds
        self._transport = transport

    async def _request(self, method: str, table: str, *, params=None, json=None, headers=None) -> list[dict]:
        try:
            async with httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(
                    method, f"{self._base}/{table}", params=params, json=json, headers=headers
                )
        except httpx.HTTPError as exc:
            raise RepositoryError(f"Supabase is not reachable: {exc!r}") from exc
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            message = body.get("message") or response.text
            raise RepositoryError(
                f"Supabase {method} {table} failed: {message}", response.status_code, body.get("code")
            )
        return response.json() if response.content else []

    # ── Projects ──

    async def create_project(self, project: dict) -> dict:
        rows = await self._request("POST", "projects", json=project, headers=RETURN_ROWS)
        return rows[0]

    async def list_projects(self) -> list[dict]:
        rows = await self._request(
            "GET",
            "projects",
            params={
                "select": "*,photos(id,elevation,is_primary,status,thumbnail_path,created_at),segments(count)",
                "order": "updated_at.desc",
                "photos.order": "created_at.asc",
            },
        )
        for row in rows:
            counts = row.pop("segments", None) or [{"count": 0}]
            row["segment_count"] = counts[0]["count"]
        return rows

    async def get_project(self, project_id: str) -> dict | None:
        rows = await self._request(
            "GET",
            "projects",
            params={
                "id": f"eq.{project_id}",
                "select": "*,photos(*,jobs(*)),segments(*),design_variants(*,segment_materials(*)),"
                          "project_rate_overrides(*)",
                "photos.order": "created_at.asc",
                "design_variants.order": "created_at.asc",
                "photos.jobs.order": "created_at.desc",
                "photos.jobs.limit": "1",
                "segments.order": "label.asc,created_at.asc",
            },
        )
        if not rows:
            return None
        row = rows[0]
        for photo in row["photos"]:
            jobs = photo.pop("jobs", [])
            photo["latest_job"] = jobs[0] if jobs else None
        variants = row.pop("design_variants", [])
        for variant in variants:
            variant["assignments"] = variant.pop("segment_materials", [])
        row["variants"] = variants
        row["rate_overrides"] = row.pop("project_rate_overrides", [])
        return row

    async def update_project(self, project_id: str, fields: dict) -> dict | None:
        rows = await self._request(
            "PATCH", "projects", params={"id": f"eq.{project_id}"}, json=fields, headers=RETURN_ROWS
        )
        return rows[0] if rows else None

    async def delete_project(self, project_id: str) -> bool:
        rows = await self._request(
            "DELETE", "projects", params={"id": f"eq.{project_id}"}, headers=RETURN_ROWS
        )
        return bool(rows)

    # ── Photos ──

    async def create_photos(self, photos: list[dict]) -> list[dict]:
        return await self._request("POST", "photos", json=photos, headers=RETURN_ROWS)

    async def get_photo(self, photo_id: str) -> dict | None:
        rows = await self._request("GET", "photos", params={"id": f"eq.{photo_id}", "select": "*"})
        return rows[0] if rows else None

    async def update_photo(self, photo_id: str, fields: dict) -> dict | None:
        rows = await self._request(
            "PATCH", "photos", params={"id": f"eq.{photo_id}"}, json=fields, headers=RETURN_ROWS
        )
        return rows[0] if rows else None

    async def delete_photo(self, photo_id: str) -> bool:
        rows = await self._request("DELETE", "photos", params={"id": f"eq.{photo_id}"}, headers=RETURN_ROWS)
        return bool(rows)

    # ── Jobs ──

    async def create_job(self, job: dict) -> dict:
        rows = await self._request("POST", "jobs", json=job, headers=RETURN_ROWS)
        return rows[0]

    async def get_job(self, job_id: str) -> dict | None:
        rows = await self._request("GET", "jobs", params={"id": f"eq.{job_id}", "select": "*"})
        return rows[0] if rows else None

    async def update_job(self, job_id: str, fields: dict) -> dict | None:
        rows = await self._request(
            "PATCH", "jobs", params={"id": f"eq.{job_id}"}, json=fields, headers=RETURN_ROWS
        )
        return rows[0] if rows else None

    # ── Segments ──

    async def get_segment(self, segment_id: str) -> dict | None:
        rows = await self._request("GET", "segments", params={"id": f"eq.{segment_id}", "select": "*"})
        return rows[0] if rows else None

    async def update_segment(self, segment_id: str, fields: dict) -> dict | None:
        rows = await self._request(
            "PATCH", "segments", params={"id": f"eq.{segment_id}"}, json=fields, headers=RETURN_ROWS
        )
        return rows[0] if rows else None

    async def delete_segment(self, segment_id: str) -> bool:
        rows = await self._request("DELETE", "segments", params={"id": f"eq.{segment_id}"}, headers=RETURN_ROWS)
        return bool(rows)

    async def confirm_segments(self, photo_id: str) -> None:
        await self._request("PATCH", "segments", params={"photo_id": f"eq.{photo_id}"}, json={"is_confirmed": True})

    async def replace_auto_segments(self, photo_id: str, segments: list[dict]) -> None:
        await self._request(
            "DELETE", "segments", params={"photo_id": f"eq.{photo_id}", "source": "eq.auto"}
        )
        if segments:
            await self._request("POST", "segments", json=segments)

    # ── Materials & design variants ──

    async def list_materials(self) -> list[dict]:
        return await self._request(
            "GET", "materials", params={"select": "*", "is_active": "eq.true", "order": "category.asc,name.asc"}
        )

    async def create_variant(self, variant: dict) -> dict:
        rows = await self._request("POST", "design_variants", json=variant, headers=RETURN_ROWS)
        return {**rows[0], "assignments": []}

    async def get_variant(self, variant_id: str) -> dict | None:
        rows = await self._request(
            "GET", "design_variants", params={"id": f"eq.{variant_id}", "select": "*,segment_materials(*)"}
        )
        if not rows:
            return None
        row = rows[0]
        row["assignments"] = row.pop("segment_materials", [])
        return row

    async def update_variant(self, variant_id: str, fields: dict) -> dict | None:
        rows = await self._request(
            "PATCH", "design_variants", params={"id": f"eq.{variant_id}"}, json=fields, headers=RETURN_ROWS
        )
        return rows[0] if rows else None

    async def delete_variant(self, variant_id: str) -> bool:
        rows = await self._request(
            "DELETE", "design_variants", params={"id": f"eq.{variant_id}"}, headers=RETURN_ROWS
        )
        return bool(rows)

    async def upsert_assignments(self, rows: list[dict]) -> None:
        if rows:
            await self._request(
                "POST", "segment_materials", params={"on_conflict": "variant_id,segment_id"}, json=rows,
                headers={"Prefer": "resolution=merge-duplicates"},
            )

    async def delete_assignments(self, variant_id: str, segment_ids: list[str]) -> None:
        if segment_ids:
            await self._request("DELETE", "segment_materials", params={
                "variant_id": f"eq.{variant_id}", "segment_id": f"in.({','.join(segment_ids)})",
            })

    async def delete_segment_assignments(self, segment_id: str) -> None:
        await self._request("DELETE", "segment_materials", params={"segment_id": f"eq.{segment_id}"})

    async def upsert_rate_override(self, row: dict) -> None:
        await self._request(
            "POST", "project_rate_overrides", params={"on_conflict": "project_id,material_id"}, json=row,
            headers={"Prefer": "resolution=merge-duplicates"},
        )

    async def delete_rate_override(self, project_id: str, material_id: str) -> None:
        await self._request("DELETE", "project_rate_overrides", params={
            "project_id": f"eq.{project_id}", "material_id": f"eq.{material_id}",
        })
