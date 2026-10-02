"""
In-memory repository for tests and offline development (`storage.backend: "local"`).

Data is lost when the process stops. Scoping by user mirrors the Row Level Security
policies in supabase/schema.sql: a user never sees another user's rows. The
one-primary-photo-per-elevation rule mirrors the database's unique index.
"""
import copy
import uuid
from datetime import datetime, timezone

from app.repositories.base import RepositoryError

PHOTO_SUMMARY_FIELDS = ("id", "elevation", "is_primary", "status", "thumbnail_path", "created_at")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryStore:
    def __init__(self):
        self.projects: dict[str, dict] = {}
        self.photos: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.segments: dict[str, dict] = {}


class MemoryRepository:
    def __init__(self, store: MemoryStore, user_id: str):
        self._store = store
        self._user_id = str(user_id)

    def _owned(self, project_id) -> dict | None:
        project = self._store.projects.get(str(project_id))
        return project if project and project["user_id"] == self._user_id else None

    def _owned_photo(self, photo_id) -> dict | None:
        photo = self._store.photos.get(str(photo_id))
        return photo if photo and self._owned(photo["project_id"]) else None

    def _photos_of(self, project_id: str) -> list[dict]:
        return sorted(
            (p for p in self._store.photos.values() if p["project_id"] == project_id),
            key=lambda p: p["created_at"],
        )

    def _check_one_primary(self, project_id: str) -> None:
        primaries = [p["elevation"] for p in self._photos_of(project_id) if p["is_primary"]]
        if len(primaries) != len(set(primaries)):
            raise RepositoryError("duplicate key value violates photos_one_primary_per_elevation", 409, "23505")

    # ── Projects ──

    async def create_project(self, project: dict) -> dict:
        now = _now()
        row = {"id": str(uuid.uuid4()), **copy.deepcopy(project), "user_id": self._user_id,
               "created_at": now, "updated_at": now}
        row["id"] = str(row["id"])
        self._store.projects[row["id"]] = row
        return copy.deepcopy(row)

    async def list_projects(self) -> list[dict]:
        rows = []
        for project in self._store.projects.values():
            if project["user_id"] != self._user_id:
                continue
            row = copy.deepcopy(project)
            row["photos"] = [{k: p[k] for k in PHOTO_SUMMARY_FIELDS} for p in self._photos_of(project["id"])]
            row["segment_count"] = sum(1 for s in self._store.segments.values() if s["project_id"] == project["id"])
            rows.append(row)
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    async def get_project(self, project_id: str) -> dict | None:
        project = self._owned(project_id)
        if project is None:
            return None
        row = copy.deepcopy(project)
        row["photos"] = []
        for photo in self._photos_of(row["id"]):
            jobs = sorted((j for j in self._store.jobs.values() if j["photo_id"] == photo["id"]),
                          key=lambda j: j["created_at"])
            row["photos"].append({**copy.deepcopy(photo), "latest_job": copy.deepcopy(jobs[-1]) if jobs else None})
        row["segments"] = sorted(
            (copy.deepcopy(s) for s in self._store.segments.values() if s["project_id"] == row["id"]),
            key=lambda s: (s["label"], s["created_at"]),
        )
        return row

    async def update_project(self, project_id: str, fields: dict) -> dict | None:
        project = self._owned(project_id)
        if project is None:
            return None
        project.update(copy.deepcopy(fields), updated_at=_now())
        return copy.deepcopy(project)

    async def delete_project(self, project_id: str) -> bool:
        if self._owned(project_id) is None:
            return False
        project_id = str(project_id)
        del self._store.projects[project_id]
        for table in (self._store.photos, self._store.jobs, self._store.segments):
            for key in [k for k, v in table.items() if v["project_id"] == project_id]:
                del table[key]
        return True

    # ── Photos ──

    async def create_photos(self, photos: list[dict]) -> list[dict]:
        created = []
        for photo in photos:
            if self._owned(photo["project_id"]) is None:
                raise RepositoryError("new row violates row-level security policy", 403, "42501")
            row = {"id": str(uuid.uuid4()), "elevation": "front", "is_primary": False, "status": "uploaded",
                   "image_meta": {}, "quality_report": {}, "measurement": {}, "created_at": _now(),
                   **copy.deepcopy(photo)}
            row["id"], row["project_id"] = str(row["id"]), str(row["project_id"])
            self._store.photos[row["id"]] = row
            created.append(row)
        if created:
            self._check_one_primary(created[0]["project_id"])
        return copy.deepcopy(created)

    async def get_photo(self, photo_id: str) -> dict | None:
        photo = self._owned_photo(photo_id)
        return copy.deepcopy(photo) if photo else None

    async def update_photo(self, photo_id: str, fields: dict) -> dict | None:
        photo = self._owned_photo(photo_id)
        if photo is None:
            return None
        before = copy.deepcopy(photo)
        photo.update(copy.deepcopy(fields))
        try:
            self._check_one_primary(photo["project_id"])
        except RepositoryError:
            photo.clear()
            photo.update(before)
            raise
        return copy.deepcopy(photo)

    async def delete_photo(self, photo_id: str) -> bool:
        photo = self._owned_photo(photo_id)
        if photo is None:
            return False
        del self._store.photos[photo["id"]]
        for table in (self._store.jobs, self._store.segments):
            for key in [k for k, v in table.items() if v["photo_id"] == photo["id"]]:
                del table[key]
        return True

    # ── Jobs ──

    async def create_job(self, job: dict) -> dict:
        if self._owned_photo(job["photo_id"]) is None:
            raise RepositoryError("new row violates row-level security policy", 403, "42501")
        row = {"id": str(uuid.uuid4()), "kind": "analyze", "status": "queued", "stage": None, "progress": 0,
               "error": None, "result_meta": {}, "created_at": _now(), "started_at": None,
               "finished_at": None, **copy.deepcopy(job)}
        row["project_id"], row["photo_id"] = str(row["project_id"]), str(row["photo_id"])
        self._store.jobs[row["id"]] = row
        return copy.deepcopy(row)

    async def get_job(self, job_id: str) -> dict | None:
        job = self._store.jobs.get(str(job_id))
        if job is None or self._owned(job["project_id"]) is None:
            return None
        return copy.deepcopy(job)

    async def update_job(self, job_id: str, fields: dict) -> dict | None:
        job = self._store.jobs.get(str(job_id))
        if job is None or self._owned(job["project_id"]) is None:
            return None
        job.update(copy.deepcopy(fields))
        return copy.deepcopy(job)

    # ── Segments ──

    def _owned_segment(self, segment_id) -> dict | None:
        segment = self._store.segments.get(str(segment_id))
        return segment if segment and self._owned(segment["project_id"]) else None

    async def get_segment(self, segment_id: str) -> dict | None:
        segment = self._owned_segment(segment_id)
        return copy.deepcopy(segment) if segment else None

    async def update_segment(self, segment_id: str, fields: dict) -> dict | None:
        segment = self._owned_segment(segment_id)
        if segment is None:
            return None
        segment.update(copy.deepcopy(fields))
        return copy.deepcopy(segment)

    async def delete_segment(self, segment_id: str) -> bool:
        segment = self._owned_segment(segment_id)
        if segment is None:
            return False
        del self._store.segments[segment["id"]]
        return True

    async def confirm_segments(self, photo_id: str) -> None:
        if self._owned_photo(photo_id) is None:
            return
        for segment in self._store.segments.values():
            if segment["photo_id"] == str(photo_id):
                segment["is_confirmed"] = True

    async def replace_auto_segments(self, photo_id: str, segments: list[dict]) -> None:
        photo = self._owned_photo(photo_id)
        if photo is None:
            raise RepositoryError("new row violates row-level security policy", 403, "42501")
        for key in [k for k, s in self._store.segments.items()
                    if s["photo_id"] == photo["id"] and s["source"] == "auto"]:
            del self._store.segments[key]
        for segment in segments:
            row = {"id": str(uuid.uuid4()), "source": "auto", "confidence": None, "area_sqm": None,
                   "length_m": None, "scale_source": None, "user_dimension": None, "depth_stats": None,
                   "is_confirmed": False, "created_at": _now(), **copy.deepcopy(segment)}
            self._store.segments[row["id"]] = row
