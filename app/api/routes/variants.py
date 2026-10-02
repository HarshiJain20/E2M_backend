"""Materials catalog and design variants (requirement 5.3)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.routes.projects import owned_project, project_detail
from app.core.deps import get_repository, get_storage
from app.repositories.base import Repository, RepositoryError
from app.schemas.project import AssignmentIn, MaterialOut, ProjectDetail, VariantCreate, VariantUpdate
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
