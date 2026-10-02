"""Review detected regions: relabel or delete (requirement 5.2)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.projects import owned_project, project_detail
from app.core.deps import get_repository, get_storage
from app.domain import measure_type
from app.repositories.base import Repository
from app.schemas.project import ProjectDetail, SegmentSize, SegmentUpdate
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
    fields = {"label": payload.label, "measure_type": measure_type(payload.label)}
    if fields["measure_type"] != segment["measure_type"]:
        fields["user_dimension"] = None  # an area the user entered cannot become a length (or the reverse)
    await repo.update_segment(str(segment_id), fields)
    if payload.label != segment["label"]:
        await repo.delete_segment_assignments(str(segment_id))  # e.g. paint does not fit a railing
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)


@router.put("/{segment_id}/size", response_model=ProjectDetail)
async def set_exact_size(
    segment_id: uuid.UUID,
    payload: SegmentSize,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    """Use a size the user measured instead of the estimate (requirement 5.5)."""
    segment = await _owned_segment(segment_id, repo)
    is_length = measure_type(segment["label"]) == "length"
    if is_length != (payload.length_m is not None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Give a length for railings and roof edges, and width × height or an area for surfaces.",
        )
    await repo.update_segment(str(segment_id), {"user_dimension": payload.model_dump(exclude_none=True)})
    return await project_detail(await owned_project(str(segment["project_id"]), repo), storage)


@router.delete("/{segment_id}/size", response_model=ProjectDetail)
async def clear_exact_size(
    segment_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    segment = await _owned_segment(segment_id, repo)
    await repo.update_segment(str(segment_id), {"user_dimension": None})
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
