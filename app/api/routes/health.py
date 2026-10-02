"""Foundation health endpoints."""
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def api_health_check() -> dict[str, str]:
    """Confirm that the versioned API is reachable."""
    settings = get_settings()
    return {"status": "ok", "service": settings.app.name, "version": settings.app.version}

