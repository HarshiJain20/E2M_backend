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
                "select": "*,photos(*,jobs(*)),segments(*)",
                "photos.order": "created_at.asc",
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

    async def replace_auto_segments(self, photo_id: str, segments: list[dict]) -> None:
        await self._request(
            "DELETE", "segments", params={"photo_id": f"eq.{photo_id}", "source": "eq.auto"}
        )
        if segments:
            await self._request("POST", "segments", json=segments)
