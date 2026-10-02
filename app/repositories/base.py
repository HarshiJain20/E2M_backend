"""
Data access for one signed-in user.

Every repository instance is scoped to a single user: it can only see and change that
user's rows. With Supabase this is enforced by Row Level Security on the user's token;
the in-memory implementation mirrors the same rule for tests and offline development.
Rows are plain dicts shaped like the database columns.
"""
from typing import Protocol


class RepositoryError(RuntimeError):
    """The data service rejected or failed a request."""

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code  # PostgREST / Postgres error code, e.g. PGRST205 (table missing)


class Repository(Protocol):
    # ── Projects ──
    async def create_project(self, project: dict) -> dict: ...

    async def list_projects(self) -> list[dict]:
        """Newest first; each row has `photos` (summary fields) and `segment_count`."""

    async def get_project(self, project_id: str) -> dict | None:
        """Row plus `photos` (oldest first, each with `latest_job`) and `segments`."""

    async def update_project(self, project_id: str, fields: dict) -> dict | None: ...

    async def delete_project(self, project_id: str) -> bool: ...

    # ── Photos ──
    async def create_photos(self, photos: list[dict]) -> list[dict]: ...

    async def get_photo(self, photo_id: str) -> dict | None: ...

    async def update_photo(self, photo_id: str, fields: dict) -> dict | None: ...

    async def delete_photo(self, photo_id: str) -> bool: ...

    # ── Jobs ──
    async def create_job(self, job: dict) -> dict: ...

    async def get_job(self, job_id: str) -> dict | None: ...

    async def update_job(self, job_id: str, fields: dict) -> dict | None: ...

    # ── Segments ──
    async def get_segment(self, segment_id: str) -> dict | None: ...

    async def update_segment(self, segment_id: str, fields: dict) -> dict | None: ...

    async def delete_segment(self, segment_id: str) -> bool: ...

    async def confirm_segments(self, photo_id: str) -> None:
        """Mark every segment of the photo as reviewed by the user."""

    async def replace_auto_segments(self, photo_id: str, segments: list[dict]) -> None:
        """Delete the photo's auto-detected segments and insert new ones."""
