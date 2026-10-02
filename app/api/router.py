"""Versioned HTTP API composition."""
from fastapi import APIRouter

from app.api.routes import health, jobs, photos, projects, segments

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(projects.router)
api_router.include_router(photos.router)
api_router.include_router(segments.router)
api_router.include_router(jobs.router)
