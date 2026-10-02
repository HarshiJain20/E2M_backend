"""
Object storage for project photos.

`SupabaseStorage` keeps photos in the private `project-images` bucket, acting as the
signed-in user (publishable key + user token); storage policies in supabase/schema.sql
limit each user to their own `<user_id>/...` folder. `LocalStorage` writes under
storage.upload_dir for offline development and tests; the app serves those files at
/api/v1/media.
"""
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    async def put(self, path: str, data: bytes, content_type: str) -> None: ...
    async def get(self, path: str) -> bytes: ...
    async def delete(self, paths: list[str]) -> None: ...
    async def signed_urls(self, paths: list[str]) -> dict[str, str]: ...


class SupabaseStorage:
    def __init__(self, settings: Settings, access_token: str, transport: httpx.AsyncBaseTransport | None = None):
        self._base = f"{settings.supabase.url.rstrip('/')}/storage/v1"
        self._bucket = settings.supabase.storage_bucket
        self._ttl = settings.supabase.signed_url_ttl_seconds
        self._headers = {
            "apikey": settings.supabase.publishable_key,
            "Authorization": f"Bearer {access_token}",
        }
        self._timeout = settings.supabase.timeout_seconds
        self._transport = transport

    async def _request(self, method: str, url: str, action: str, **kwargs) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                headers=self._headers, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.request(method, f"{self._base}{url}", **kwargs)
        except httpx.HTTPError as exc:
            raise StorageError(f"Supabase Storage is not reachable: {exc!r}") from exc
        if response.is_error:
            raise StorageError(
                f"Supabase Storage {action} failed ({response.status_code}): {response.text[:300]}"
            )
        return response

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        await self._request(
            "POST", f"/object/{self._bucket}/{path}", "upload",
            content=data, headers={"Content-Type": content_type, "x-upsert": "true"},
        )

    async def get(self, path: str) -> bytes:
        response = await self._request("GET", f"/object/authenticated/{self._bucket}/{path}", "download")
        return response.content

    async def delete(self, paths: list[str]) -> None:
        if paths:
            await self._request("DELETE", f"/object/{self._bucket}", "delete", json={"prefixes": paths})

    async def signed_urls(self, paths: list[str]) -> dict[str, str]:
        if not paths:
            return {}
        response = await self._request(
            "POST", f"/object/sign/{self._bucket}", "signing",
            json={"expiresIn": self._ttl, "paths": paths},
        )
        return {
            item["path"]: f"{self._base}{item['signedURL']}"
            for item in response.json()
            if item.get("signedURL")
        }


class LocalStorage:
    def __init__(self, settings: Settings):
        self._root = settings.storage.upload_path

    def _resolve(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not target.is_relative_to(self._root):
            raise StorageError(f"Invalid storage path: {path}")
        return target

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
        # Like Supabase, only existing files get a URL (callers use this to check existence).
        return {path: f"/api/v1/media/{path}" for path in paths if self._resolve(path).is_file()}
