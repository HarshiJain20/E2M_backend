"""
Object storage for project images.

`SupabaseStorage` keeps images in a private Supabase Storage bucket and hands the
browser short-lived signed URLs. `LocalStorage` writes under UPLOAD_DIR for offline
development and tests; its files are served by the app at /api/v1/media.
"""
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    async def ensure_ready(self) -> None: ...
    async def put(self, path: str, data: bytes, content_type: str) -> None: ...
    async def get(self, path: str) -> bytes: ...
    async def delete(self, paths: list[str]) -> None: ...
    async def signed_urls(self, paths: list[str]) -> dict[str, str]: ...


class SupabaseStorage:
    def __init__(self, settings: Settings):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
            raise StorageError(
                "E2M_SUPABASE_URL and E2M_SUPABASE_SECRET_KEY are required for Supabase Storage"
            )
        key = settings.SUPABASE_SECRET_KEY
        headers = {"apikey": key}
        # Legacy service_role keys are JWTs and also go in Authorization; sb_secret_ keys must not.
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        self._base = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1"
        self._bucket = settings.SUPABASE_STORAGE_BUCKET
        self._ttl = settings.SIGNED_URL_TTL_SECONDS
        self._max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        self._client = httpx.AsyncClient(headers=headers, timeout=60.0)

    async def _check(self, response: httpx.Response, action: str) -> httpx.Response:
        if response.is_error:
            raise StorageError(f"Supabase Storage {action} failed ({response.status_code}): {response.text[:300]}")
        return response

    async def ensure_ready(self) -> None:
        response = await self._client.get(f"{self._base}/bucket/{self._bucket}")
        if response.status_code == 200:
            return
        created = await self._client.post(
            f"{self._base}/bucket",
            json={
                "id": self._bucket,
                "name": self._bucket,
                "public": False,
                "file_size_limit": self._max_bytes,
                "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
            },
        )
        if created.is_error and "already exists" not in created.text.lower():
            await self._check(created, "bucket creation")

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        response = await self._client.post(
            f"{self._base}/object/{self._bucket}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        await self._check(response, "upload")

    async def get(self, path: str) -> bytes:
        response = await self._client.get(f"{self._base}/object/authenticated/{self._bucket}/{path}")
        return (await self._check(response, "download")).content

    async def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        response = await self._client.request(
            "DELETE", f"{self._base}/object/{self._bucket}", json={"prefixes": paths}
        )
        await self._check(response, "delete")

    async def signed_urls(self, paths: list[str]) -> dict[str, str]:
        if not paths:
            return {}
        response = await self._client.post(
            f"{self._base}/object/sign/{self._bucket}",
            json={"expiresIn": self._ttl, "paths": paths},
        )
        await self._check(response, "signing")
        return {
            item["path"]: f"{self._base}{item['signedURL']}"
            for item in response.json()
            if item.get("signedURL")
        }


class LocalStorage:
    def __init__(self, settings: Settings):
        self._root = Path(settings.UPLOAD_DIR).resolve()

    def _resolve(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not target.is_relative_to(self._root):
            raise StorageError(f"Invalid storage path: {path}")
        return target

    async def ensure_ready(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def get(self, path: str) -> bytes:
        try:
            return self._resolve(path).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"Missing object: {path}") from exc

    async def delete(self, paths: list[str]) -> None:
        for path in paths:
            self._resolve(path).unlink(missing_ok=True)

    async def signed_urls(self, paths: list[str]) -> dict[str, str]:
        return {path: f"/api/v1/media/{path}" for path in paths}


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.STORAGE_BACKEND == "local":
        return LocalStorage(settings)
    return SupabaseStorage(settings)
