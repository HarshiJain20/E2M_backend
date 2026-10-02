"""Project endpoints: create with photos, add photos, list, open, rename, delete."""
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.core.deps import get_repository, get_storage
from app.domain import MAX_PHOTOS_PER_PROJECT
from app.repositories.base import Repository
from app.schemas.project import PhotoOut, ProjectDetail, ProjectSummary, ProjectUpdate
from app.services.measurement import measure_photo
from app.services.photos import primary_changes, project_status, whole_house_totals
from app.services.pipeline import recover_interrupted, run_analysis, start_analysis
from app.services.storage import Storage, StorageError
from app.services.uploads import assign_elevations, prepare_photos, store_photos

router = APIRouter(prefix="/projects", tags=["projects"])


def _default_name() -> str:
    return f"Exterior project {datetime.now():%d %b %Y}"


def _cover(photos: list[dict]) -> dict | None:
    """The photo that represents the project: primary front view, else the first photo."""
    return next((p for p in photos if p["elevation"] == "front" and p["is_primary"]), photos[0] if photos else None)


async def owned_project(project_id, repo: Repository) -> dict:
    project = await repo.get_project(str(project_id))
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return project


async def project_detail(project: dict, storage: Storage) -> ProjectDetail:
    photos = project["photos"]
    urls = await storage.signed_urls(
        [path for p in photos for path in (p["working_image_path"], p["thumbnail_path"])]
    )
    raw_by_photo: dict[str, list[dict]] = {}
    for segment in project["segments"]:
        raw_by_photo.setdefault(str(segment["photo_id"]), []).append(segment)
    segments_by_photo, scales = {}, {}
    for photo in photos:
        key = str(photo["id"])
        segments_by_photo[key], scales[key] = measure_photo(photo, raw_by_photo.get(key, []))
    cover = _cover(photos)
    return ProjectDetail(
        id=project["id"],
        name=project["name"],
        status=project_status(photos),
        thumbnail_url=urls.get(cover["thumbnail_path"]) if cover else None,
        photo_count=len(photos),
        segment_count=len(project["segments"]),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
        photos=[
            PhotoOut(
                **p,
                image_url=urls.get(p["working_image_path"]),
                thumbnail_url=urls.get(p["thumbnail_path"]),
                segments=segments_by_photo.get(str(p["id"]), []),
                regions_confirmed=bool(segments_by_photo[str(p["id"])])
                and all(s["is_confirmed"] for s in segments_by_photo[str(p["id"])]),
                scale={"source": scales[str(p["id"])].source, "detail": scales[str(p["id"])].detail},
                reference=(p.get("measurement") or {}).get("reference"),
            )
            for p in photos
        ],
        totals=whole_house_totals(photos, [s for rows in segments_by_photo.values() for s in rows]),
    )


async def apply_primary_rule(project: dict, repo: Repository) -> None:
    """Make sure every elevation with photos has exactly one primary photo."""
    unset, promote = primary_changes(project["photos"])
    for photo_id in unset:  # unsets first: the database allows one primary per elevation
        await repo.update_photo(photo_id, {"is_primary": False})
    for photo_id in promote:
        await repo.update_photo(photo_id, {"is_primary": True})


async def validate_and_store(
    project_id: str, existing: list[dict], files: list[UploadFile], elevations: list[str],
    user: CurrentUser, storage: Storage,
) -> list[dict]:
    """Check every photo, then upload them. Nothing is stored if any photo is unusable."""
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one photo.")
    if len(existing) + len(files) > MAX_PHOTOS_PER_PROJECT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"A project can have up to {MAX_PHOTOS_PER_PROJECT} photos.",
        )
    sides = assign_elevations(elevations, len(files), {p["elevation"] for p in existing})
    images = await prepare_photos(files, get_settings())
    return await store_photos(storage, user.id, project_id, images, sides)


async def insert_and_analyze(
    rows: list[dict], existing: list[dict], repo: Repository, storage: Storage, background: BackgroundTasks,
) -> None:
    # The first photo of a side that has no primary yet becomes the counted one.
    covered = {p["elevation"] for p in existing if p["is_primary"]}
    for row in rows:
        if row["elevation"] not in covered:
            row["is_primary"] = True
            covered.add(row["elevation"])
    for photo in await repo.create_photos(rows):
        job = await start_analysis(photo, repo)
        background.add_task(run_analysis, str(job["id"]), photo, repo, storage)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectDetail)
async def create_project(
    background: BackgroundTasks,
    images: list[UploadFile] = File(...),
    elevations: list[str] = Form(default=[]),
    name: str | None = Form(default=None, max_length=120),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    project_id = str(uuid.uuid4())
    # Photos are validated first, so a rejected upload leaves no empty project behind.
    rows = await validate_and_store(project_id, [], images, elevations, user, storage)
    await repo.create_project({
        "id": project_id, "user_id": str(user.id), "name": (name or "").strip() or _default_name(),
    })
    await insert_and_analyze(rows, [], repo, storage, background)
    return await project_detail(await owned_project(project_id, repo), storage)


@router.post("/{project_id}/photos", status_code=status.HTTP_201_CREATED, response_model=ProjectDetail)
async def upload_more_photos(
    project_id: uuid.UUID,
    background: BackgroundTasks,
    images: list[UploadFile] = File(...),
    elevations: list[str] = Form(default=[]),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    project = await owned_project(project_id, repo)
    rows = await validate_and_store(str(project_id), project["photos"], images, elevations, user, storage)
    await insert_and_analyze(rows, project["photos"], repo, storage, background)
    await repo.update_project(str(project_id), {"name": project["name"]})  # bumps updated_at
    return await project_detail(await owned_project(project_id, repo), storage)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> list[ProjectSummary]:
    projects = await repo.list_projects()
    covers = {p["id"]: _cover(p["photos"]) for p in projects}
    urls = await storage.signed_urls([c["thumbnail_path"] for c in covers.values() if c])
    return [
        ProjectSummary(
            id=p["id"],
            name=p["name"],
            status=project_status(p["photos"]),
            thumbnail_url=urls.get(covers[p["id"]]["thumbnail_path"]) if covers[p["id"]] else None,
            photo_count=len(p["photos"]),
            segment_count=p["segment_count"],
            created_at=p["created_at"],
            updated_at=p["updated_at"],
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    project = await recover_interrupted(await owned_project(project_id, repo), repo)
    return await project_detail(project, storage)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    if await repo.update_project(str(project_id), {"name": payload.name.strip()}) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return await project_detail(await owned_project(project_id, repo), storage)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> Response:
    project = await owned_project(project_id, repo)
    await repo.delete_project(str(project_id))
    try:
        await storage.delete([
            path for p in project["photos"]
            for path in (p["original_image_path"], p["working_image_path"], p["thumbnail_path"])
        ])
    except StorageError:
        pass  # orphaned files are harmless; the project record is gone
    return Response(status_code=status.HTTP_204_NO_CONTENT)
