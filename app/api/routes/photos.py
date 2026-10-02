"""Photo endpoints: change side, choose the counted photo, re-run analysis, remove."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.routes.projects import apply_primary_rule, owned_project, project_detail
from app.core.deps import get_repository, get_storage
from app.domain import JobStatus
from app.repositories.base import Repository
from app.schemas.project import JobOut, PhotoUpdate, ProjectDetail, ReferenceIn
from app.services.pipeline import recover_interrupted, run_analysis, start_analysis
from app.services.storage import Storage, StorageError

router = APIRouter(prefix="/photos", tags=["photos"])


async def _owned_photo(photo_id: uuid.UUID, repo: Repository) -> dict:
    photo = await repo.get_photo(str(photo_id))
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found.")
    return photo


@router.patch("/{photo_id}", response_model=ProjectDetail)
async def update_photo(
    photo_id: uuid.UUID,
    payload: PhotoUpdate,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    photo = await _owned_photo(photo_id, repo)
    project_id = str(photo["project_id"])

    if payload.elevation and payload.elevation != photo["elevation"]:
        # Move without primary status; the rule below picks the counted photo on both sides.
        await repo.update_photo(str(photo_id), {"elevation": payload.elevation, "is_primary": False})
        photo = {**photo, "elevation": payload.elevation, "is_primary": False}

    if payload.is_primary and not photo["is_primary"]:
        project = await owned_project(project_id, repo)
        for other in project["photos"]:
            if other["elevation"] == photo["elevation"] and other["is_primary"]:
                await repo.update_photo(str(other["id"]), {"is_primary": False})
        await repo.update_photo(str(photo_id), {"is_primary": True})

    await apply_primary_rule(await owned_project(project_id, repo), repo)
    return await project_detail(await owned_project(project_id, repo), storage)


@router.delete("/{photo_id}", response_model=ProjectDetail)
async def delete_photo(
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    photo = await _owned_photo(photo_id, repo)
    project_id = str(photo["project_id"])
    project = await owned_project(project_id, repo)
    if len(project["photos"]) == 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A project needs at least one photo. Delete the project instead."
        )

    await repo.delete_photo(str(photo_id))
    try:
        await storage.delete([photo["original_image_path"], photo["working_image_path"], photo["thumbnail_path"]])
    except StorageError:
        pass  # orphaned files are harmless; the photo record is gone
    await apply_primary_rule(await owned_project(project_id, repo), repo)
    return await project_detail(await owned_project(project_id, repo), storage)


@router.put("/{photo_id}/reference", response_model=ProjectDetail)
async def set_reference(
    photo_id: uuid.UUID,
    payload: ReferenceIn,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    """Use the user's measurement of one region to scale every size in this photo."""
    photo = await _owned_photo(photo_id, repo)
    segment = await repo.get_segment(str(payload.segment_id))
    if segment is None or str(segment["photo_id"]) != str(photo_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a region from this photo.")
    measurement = {**(photo.get("measurement") or {}), "reference": payload.model_dump(mode="json")}
    await repo.update_photo(str(photo_id), {"measurement": measurement})
    return await project_detail(await owned_project(str(photo["project_id"]), repo), storage)


@router.delete("/{photo_id}/reference", response_model=ProjectDetail)
async def clear_reference(
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    photo = await _owned_photo(photo_id, repo)
    measurement = {**(photo.get("measurement") or {}), "reference": None}
    await repo.update_photo(str(photo_id), {"measurement": measurement})
    return await project_detail(await owned_project(str(photo["project_id"]), repo), storage)


@router.post("/{photo_id}/confirm", response_model=ProjectDetail)
async def confirm_regions(
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    """The user has reviewed this photo's regions (requirement 5.2)."""
    photo = await _owned_photo(photo_id, repo)
    await repo.confirm_segments(str(photo_id))
    return await project_detail(await owned_project(str(photo["project_id"]), repo), storage)


@router.post("/{photo_id}/analyze", status_code=status.HTTP_202_ACCEPTED, response_model=JobOut)
async def analyze_photo(
    photo_id: uuid.UUID,
    background: BackgroundTasks,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> JobOut:
    photo = await _owned_photo(photo_id, repo)
    project = await recover_interrupted(await owned_project(str(photo["project_id"]), repo), repo)
    current = next(p for p in project["photos"] if str(p["id"]) == str(photo_id))
    job = current.get("latest_job")
    if job and job["status"] in JobStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This photo is already being analysed.")
    job = await start_analysis(photo, repo)
    background.add_task(run_analysis, str(job["id"]), photo, repo, storage)
    return JobOut(**job)
