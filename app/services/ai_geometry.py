"""HTTP client for the E2M_ai-geometry Ray Serve application."""
import httpx

from app.core.config import get_settings


class AIGeometryError(RuntimeError):
    """The geometry service is unreachable or returned an error."""


async def analyze_image(image: bytes, filename: str = "working.jpg") -> dict:
    """Run segmentation, depth and measurement on a working image."""
    settings = get_settings()
    url = f"{settings.ai_geometry.url.rstrip('/')}/v1/analyze"
    try:
        headers = {"X-API-Key": settings.ai_geometry.api_key} if settings.ai_geometry.api_key else {}
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
