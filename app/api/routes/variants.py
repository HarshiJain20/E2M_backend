"""Materials catalog and design variants (requirement 5.3)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.routes.projects import owned_project, project_detail
from app.core.deps import get_repository, get_storage
from app.repositories.base import Repository, RepositoryError
from app.schemas.project import AssignmentIn, MaterialOut, PhotorealOut, ProjectDetail, VariantCreate, VariantUpdate
from app.services.measurement import focal_length_px, measure_project
import hashlib
import posixpath

from app.services import ai_geometry
from app.services.render import photoreal_prompt, region_mask_png, render_design
from app.services.storage import Storage

router = APIRouter(tags=["materials"])


@router.get("/materials", response_model=list[MaterialOut])
async def list_materials(repo: Repository = Depends(get_repository)) -> list[dict]:
    return await repo.list_materials()


def _name_taken(exc: RepositoryError, name: str) -> HTTPException:
    if exc.code == "23505":
        return HTTPException(status.HTTP_409_CONFLICT, f'A design named "{name}" already exists.')
    raise exc


async def _owned_variant(variant_id: uuid.UUID, repo: Repository) -> dict:
    variant = await repo.get_variant(str(variant_id))
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found.")
    return variant


@router.post("/projects/{project_id}/variants", status_code=status.HTTP_201_CREATED, response_model=ProjectDetail)
async def create_variant(
    project_id: uuid.UUID,
    payload: VariantCreate,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    await owned_project(project_id, repo)
    source = await _owned_variant(payload.copy_from, repo) if payload.copy_from else None
    if source and str(source["project_id"]) != str(project_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Copy a design from this project.")
    try:
        variant = await repo.create_variant({"project_id": str(project_id), "name": payload.name.strip()})
    except RepositoryError as exc:
        raise _name_taken(exc, payload.name.strip()) from exc
    if source:
        await repo.upsert_assignments([
            {"variant_id": str(variant["id"]), "segment_id": str(a["segment_id"]),
             "material_id": str(a["material_id"]), "color": a.get("color")}
            for a in source["assignments"]
        ])
    return await project_detail(await owned_project(project_id, repo), storage)


@router.patch("/variants/{variant_id}", response_model=ProjectDetail)
async def rename_variant(
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    variant = await _owned_variant(variant_id, repo)
    try:
        await repo.update_variant(str(variant_id), {"name": payload.name.strip()})
    except RepositoryError as exc:
        raise _name_taken(exc, payload.name.strip()) from exc
    return await project_detail(await owned_project(str(variant["project_id"]), repo), storage)


@router.delete("/variants/{variant_id}", response_model=ProjectDetail)
async def delete_variant(
    variant_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    variant = await _owned_variant(variant_id, repo)
    await repo.delete_variant(str(variant_id))
    return await project_detail(await owned_project(str(variant["project_id"]), repo), storage)


@router.put("/variants/{variant_id}/assignments", response_model=ProjectDetail)
async def assign_material(
    variant_id: uuid.UUID,
    payload: AssignmentIn,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    variant = await _owned_variant(variant_id, repo)
    project = await owned_project(str(variant["project_id"]), repo)
    material = next((m for m in await repo.list_materials() if str(m["id"]) == str(payload.material_id)), None)
    if material is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That material is not in the catalog.")

    segments = {str(s["id"]): s for s in project["segments"]}
    chosen = [segments.get(str(sid)) for sid in payload.segment_ids]
    if any(s is None for s in chosen):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose regions from this project.")
    unsuitable = sorted({s["label"] for s in chosen if s["label"] not in material["applies_to"]})
    if unsuitable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{material['name']} can't be used on: {', '.join(l.replace('_', ' ') for l in unsuitable)}.",
        )

    color = (payload.color or material.get("swatch")) if material.get("colorable") else None
    await repo.upsert_assignments([
        {"variant_id": str(variant_id), "segment_id": str(s["id"]), "material_id": str(material["id"]), "color": color}
        for s in chosen
    ])
    return await project_detail(await owned_project(str(variant["project_id"]), repo), storage)


@router.delete("/variants/{variant_id}/assignments", response_model=ProjectDetail)
async def clear_material(
    variant_id: uuid.UUID,
    segment_ids: list[uuid.UUID] = Query(min_length=1),
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> ProjectDetail:
    variant = await _owned_variant(variant_id, repo)
    await repo.delete_assignments(str(variant_id), [str(s) for s in segment_ids])
    return await project_detail(await owned_project(str(variant["project_id"]), repo), storage)


async def _draft(variant_id: uuid.UUID, photo_id: uuid.UUID, repo: Repository, storage: Storage):
    """Everything a render needs: the photo, its measured regions, materials and the overlay draft."""
    variant = await _owned_variant(variant_id, repo)
    project = await owned_project(str(variant["project_id"]), repo)
    photo = next((p for p in project["photos"] if str(p["id"]) == str(photo_id)), None)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found in this project.")
    segments_by_photo, scales = measure_project(project)
    segments = segments_by_photo[str(photo_id)]
    materials = {str(m["id"]): m for m in await repo.list_materials()}
    image = await storage.get(photo["working_image_path"])
    jpeg = await run_in_threadpool(
        render_design, image, segments, variant["assignments"], materials, scales[str(photo_id)], focal_length_px(photo),
    )
    return variant, photo, segments, materials, image, jpeg


@router.get("/variants/{variant_id}/render/{photo_id}", response_class=Response,
            responses={200: {"content": {"image/jpeg": {}}}})
async def render_variant(
    variant_id: uuid.UUID,
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> Response:
    """The photo redesigned with this design's materials (requirement 5.4). Rendered on request."""
    *_, jpeg = await _draft(variant_id, photo_id, repo, storage)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


def _photoreal_path(photo: dict, variant_id, draft: bytes) -> str:
    # The draft is deterministic, so its hash changes whenever materials, colours, regions or scale do:
    # a stored render is only ever shown for exactly the design it was made from.
    digest = hashlib.sha256(draft).hexdigest()[:20]
    return f"{posixpath.dirname(photo['working_image_path'])}/renders/{variant_id}-{digest}.jpg"


@router.get("/variants/{variant_id}/photoreal/{photo_id}", response_model=PhotorealOut)
async def get_photoreal(
    variant_id: uuid.UUID,
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> PhotorealOut:
    """The AI render for the current materials, if one has been made."""
    _, photo, _, _, _, draft = await _draft(variant_id, photo_id, repo, storage)
    path = _photoreal_path(photo, variant_id, draft)
    url = (await storage.signed_urls([path])).get(path)
    return PhotorealOut(status="ready" if url else "none", url=url)


@router.post("/variants/{variant_id}/photoreal/{photo_id}", response_model=PhotorealOut)
async def create_photoreal(
    variant_id: uuid.UUID,
    photo_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> PhotorealOut:
    """Make a photorealistic render on the AI service (SDXL + ControlNet) and keep it."""
    variant, photo, segments, materials, original, draft = await _draft(variant_id, photo_id, repo, storage)
    path = _photoreal_path(photo, variant_id, draft)
    existing = (await storage.signed_urls([path])).get(path)
    if existing:
        return PhotorealOut(status="ready", url=existing)
    if not any(str(a["segment_id"]) in {str(s["id"]) for s in segments} for a in variant["assignments"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose materials for this photo first.")
    mask = region_mask_png(segments, variant["assignments"], photo["image_width"], photo["image_height"])
    prompt = photoreal_prompt(segments, variant["assignments"], materials)
    try:
        jpeg = await ai_geometry.render_photoreal(original, draft, mask, prompt, seed=int(path[-24:-4], 16) % 2**31)
    except ai_geometry.AIGeometryError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await storage.put(path, jpeg, "image/jpeg")
    return PhotorealOut(status="ready", url=(await storage.signed_urls([path])).get(path))
