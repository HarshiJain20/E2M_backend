"""Review detected regions: relabel or delete (requirement 5.2)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.projects import owned_project, project_detail
from app.core.deps import get_repository, get_storage
from app.domain import measure_type
from app.repositories.base import Repository
from app.schemas.project import ProjectDetail, SegmentUpdate
from app.services.storage import Storage

router = APIRouter(prefix="/segments", tags=["segments"])


async def _owned_segment(segment_id: uuid.UUID, repo: Repository) -> dict:
    segment = await repo.get_segment(str(segment_id))
    if segment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found.")
    return segment


@router.patch("/{segment_id}", response_model=ProjectDetail)
async def relabel_segment(
    segment_id: uuid.UUID,
    payload: SegmentUpdate,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    segment = await _owned_segment(segment_id, repo)
    # Sizes are recomputed from the outline on every read, so only the label and type change.
    await repo.update_segment(str(segment_id), {"label": payload.label, "measure_type": measure_type(payload.label)})
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)


@router.delete("/{segment_id}", response_model=ProjectDetail)
async def delete_segment(
    segment_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    segment = await _owned_segment(segment_id, repo)
    await repo.delete_segment(str(segment_id))
    # A measurement that referred to this region no longer applies.
    photo = await repo.get_photo(str(segment["photo_id"]))
    measurement = (photo or {}).get("measurement") or {}
    if str((measurement.get("reference") or {}).get("segment_id")) == str(segment_id):
        await repo.update_photo(str(segment["photo_id"]), {"measurement": {**measurement, "reference": None}})
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)
