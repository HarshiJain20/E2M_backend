"""HTTP client for the E2M_ai-geometry service."""
import time

import httpx

from app.core.config import get_settings


class AIGeometryError(RuntimeError):
    """The geometry service is unreachable or returned an error."""


def _headers() -> dict[str, str]:
    settings = get_settings()
    # ngrok shows a browser warning page unless this header is sent; harmless elsewhere.
    headers = {"ngrok-skip-browser-warning": "1"}
    if settings.ai_geometry.api_key:
        headers["X-API-Key"] = settings.ai_geometry.api_key
    return headers


_status_cache: dict = {"at": 0.0, "value": None}
STATUS_TTL_SECONDS = 20


async def service_status() -> str:
    """"online" or "offline", checked against the service's /health (cached briefly)."""
    if _status_cache["value"] and time.monotonic() - _status_cache["at"] < STATUS_TTL_SECONDS:
        return _status_cache["value"]
    url = f"{get_settings().ai_geometry.url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.get(url, headers=_headers())
        value = "online" if response.status_code == 200 and response.json().get("status") == "ok" else "offline"
    except (httpx.HTTPError, ValueError, AttributeError):
        value = "offline"
    _status_cache.update(at=time.monotonic(), value=value)
    return value


async def analyze_image(image: bytes, filename: str = "working.jpg") -> dict:
    """Run segmentation, depth and measurement on a working image."""
    settings = get_settings()
    url = f"{settings.ai_geometry.url.rstrip('/')}/v1/analyze"
    try:
        headers = _headers()
        async with httpx.AsyncClient(timeout=settings.ai_geometry.timeout_seconds) as client:
            response = await client.post(url, files={"image": (filename, image, "image/jpeg")}, headers=headers)
    except httpx.TimeoutException as exc:
        raise AIGeometryError("The analysis service took too long to respond.") from exc
    except httpx.HTTPError as exc:
        raise AIGeometryError("The analysis service is not reachable right now.") from exc

    if response.status_code == 401:
        raise AIGeometryError("The analysis service rejected the request. Check ai_geometry.api_key in config.json.")
    if response.is_error:
        raise AIGeometryError(
            f"The analysis service returned an error ({response.status_code})."
        )
    return response.json()


async def render_photoreal(original: bytes, draft: bytes, mask_png: bytes, prompt: str, seed: int = 0) -> bytes:
    """Ask the AI service to refine a draft redesign inside the mask (SDXL + ControlNet)."""
    settings = get_settings()
    url = f"{settings.ai_geometry.url.rstrip('/')}/v1/render"
    headers = _headers()
    files = {
        "original": ("original.jpg", original, "image/jpeg"),
        "draft": ("draft.jpg", draft, "image/jpeg"),
        "mask": ("mask.png", mask_png, "image/png"),
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_geometry.timeout_seconds) as client:
            response = await client.post(url, files=files, data={"prompt": prompt, "seed": str(seed)}, headers=headers)
    except httpx.TimeoutException as exc:
        raise AIGeometryError("The photorealistic renderer took too long. Try again.") from exc
    except httpx.HTTPError as exc:
        raise AIGeometryError(
            "The photorealistic renderer is offline right now. Use the standard preview, or try again later."
        ) from exc
    if response.status_code == 401:
        raise AIGeometryError("The analysis service rejected the request. Check ai_geometry.api_key in config.json.")
    if response.status_code == 503:
        raise AIGeometryError("Photorealistic rendering is not switched on in the AI service (models.render = \"sdxl\").")
    if response.is_error:
        raise AIGeometryError(f"The photorealistic renderer returned an error ({response.status_code}).")
    return response.content
