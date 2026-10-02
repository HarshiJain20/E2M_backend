"""Quantities and cost estimate (requirements 5.6, 5.7)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.projects import owned_project
from app.core.config import get_settings
from app.core.deps import get_repository
from app.repositories.base import Repository
from app.schemas.estimate import EstimateOut, EstimateSettings, RateUpdate
from app.services.estimate import estimate_variant
from app.services.measurement import measure_project

router = APIRouter(prefix="/projects/{project_id}", tags=["estimate"])


async def build_estimate(project: dict, repo: Repository) -> EstimateOut:
    settings = get_settings()
    include_gst = (project.get("estimate_settings") or {}).get("include_gst", True)
    materials = {str(m["id"]): m for m in await repo.list_materials()}
    overrides = {str(o["material_id"]): o for o in project.get("rate_overrides", [])}
    segments_by_photo, _ = measure_project(project)
    segments = [s for rows in segments_by_photo.values() for s in rows]
    return EstimateOut(
        project_id=project["id"],
        include_gst=include_gst,
        gst_rate=settings.pricing.gst_rate,
        variants=[
            estimate_variant(v, project["photos"], segments, materials, overrides, include_gst, settings.pricing.gst_rate)
            for v in project.get("variants", [])
        ],
    )


@router.get("/estimate", response_model=EstimateOut)
async def get_estimate(project_id: uuid.UUID, repo: Repository = Depends(get_repository)) -> EstimateOut:
    return await build_estimate(await owned_project(project_id, repo), repo)


@router.put("/rates/{material_id}", response_model=EstimateOut)
async def set_rate(
    project_id: uuid.UUID, material_id: uuid.UUID, payload: RateUpdate, repo: Repository = Depends(get_repository),
) -> EstimateOut:
    """Change a rate for this project only; the shared catalog is untouched (requirement 5.7)."""
    project = await owned_project(project_id, repo)
    if not any(str(m["id"]) == str(material_id) for m in await repo.list_materials()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found.")
    current = next((o for o in project.get("rate_overrides", []) if str(o["material_id"]) == str(material_id)), {})
    await repo.upsert_rate_override({
        "project_id": str(project_id),
        "material_id": str(material_id),
        "material_rate": payload.material_rate if payload.material_rate is not None else current.get("material_rate"),
        "labor_rate": payload.labor_rate if payload.labor_rate is not None else current.get("labor_rate"),
    })
    return await build_estimate(await owned_project(project_id, repo), repo)


@router.delete("/rates/{material_id}", response_model=EstimateOut)
async def reset_rate(
    project_id: uuid.UUID, material_id: uuid.UUID, repo: Repository = Depends(get_repository),
) -> EstimateOut:
    await owned_project(project_id, repo)
    await repo.delete_rate_override(str(project_id), str(material_id))
    return await build_estimate(await owned_project(project_id, repo), repo)


@router.patch("/estimate-settings", response_model=EstimateOut)
async def update_settings(
    project_id: uuid.UUID, payload: EstimateSettings, repo: Repository = Depends(get_repository),
) -> EstimateOut:
    project = await owned_project(project_id, repo)
    settings = {**(project.get("estimate_settings") or {}), "include_gst": payload.include_gst}
    await repo.update_project(str(project_id), {"estimate_settings": settings})
    return await build_estimate(await owned_project(project_id, repo), repo)
