"""E2M FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import configuration_problems, get_settings
from app.core.errors import register_error_handlers

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Report configuration problems at startup instead of failing on the first request."""
    problems = configuration_problems(settings)
    for problem in problems:
        logger.error("config.json: %s", problem)
    if problems:
        logger.error("Fix config.json and restart the server; API calls will fail until then.")
    yield


app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix="/api/v1")

if settings.storage.backend == "local":
    # Offline development only: Supabase serves images through signed URLs instead.
    media_root = settings.storage.upload_path
    media_root.mkdir(parents=True, exist_ok=True)
    app.mount("/api/v1/media", StaticFiles(directory=media_root), name="media")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return process health without depending on PostgreSQL availability."""
    return {"status": "ok", "service": settings.app.name, "version": settings.app.version}
