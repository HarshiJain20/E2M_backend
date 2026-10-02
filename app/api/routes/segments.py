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
    fields: dict = {"label": payload.label}
    new_type = measure_type(payload.label)
    if new_type != segment["measure_type"]:
        # An area cannot become a length (or the reverse); it is re-measured in the measurement step.
        fields.update(measure_type=new_type, area_sqm=None, length_m=None)
    await repo.update_segment(str(segment_id), fields)
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)


@router.delete("/{segment_id}", response_model=ProjectDetail)
async def delete_segment(
    segment_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    segment = await _owned_segment(segment_id, repo)
    await repo.delete_segment(str(segment_id))
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)
