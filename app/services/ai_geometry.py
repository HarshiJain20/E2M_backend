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


async def render_photoreal(original: bytes, draft: bytes, mask_png: bytes, prompt: str, seed: int = 0) -> bytes:
    """Ask the AI service to refine a draft redesign inside the mask (SDXL + ControlNet)."""
    settings = get_settings()
    url = f"{settings.ai_geometry.url.rstrip('/')}/v1/render"
    headers = {"X-API-Key": settings.ai_geometry.api_key} if settings.ai_geometry.api_key else {}
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
            "The photorealistic renderer is not reachable. Start the Kaggle notebook, or use the standard preview."
        ) from exc
    if response.status_code == 401:
        raise AIGeometryError("The analysis service rejected the request. Check ai_geometry.api_key in config.json.")
    if response.status_code == 503:
        raise AIGeometryError("Photorealistic rendering is not switched on in the AI service (models.render = \"sdxl\").")
    if response.is_error:
        raise AIGeometryError(f"The photorealistic renderer returned an error ({response.status_code}).")
    return response.content
