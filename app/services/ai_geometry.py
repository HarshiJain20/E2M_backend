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
        async with httpx.AsyncClient(timeout=settings.ai_geometry.timeout_seconds) as client:
            response = await client.post(url, files={"image": (filename, image, "image/jpeg")})
    except httpx.TimeoutException as exc:
        raise AIGeometryError("The analysis service took too long to respond.") from exc
    except httpx.HTTPError as exc:
        raise AIGeometryError("The analysis service is not reachable right now.") from exc

    if response.is_error:
        raise AIGeometryError(
            f"The analysis service returned an error ({response.status_code})."
        )
    return response.json()
