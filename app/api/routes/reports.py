"""PDF report for a design (requirement 5.8)."""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool

from app.api.routes.estimate import build_estimate
from app.api.routes.projects import owned_project
from app.api.routes.variants import _owned_variant, photoreal_path, render_photo
from app.core.deps import get_repository, get_storage
from app.repositories.base import Repository
from app.services.measurement import measure_project
from app.services.reports.pdf import METHOD_NOTES, build_report
from app.services.storage import Storage

router = APIRouter(tags=["reports"])

ELEVATION_NAMES = {"front": "Front", "left": "Left side", "right": "Right side", "rear": "Rear", "other": "Other view"}


@router.get("/variants/{variant_id}/report.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def design_report(
    variant_id: uuid.UUID,
    repo: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Before/after images of every counted photo that has materials, the bill of quantities and costs."""
    variant = await _owned_variant(variant_id, repo)
    project = await owned_project(str(variant["project_id"]), repo)
    variant = next(v for v in project["variants"] if str(v["id"]) == str(variant_id))
    estimate = next(e for e in (await build_estimate(project, repo)).variants if str(e.variant_id) == str(variant_id))

    measured = measure_project(project)
    segments_by_photo, scales = measured
    materials = {str(m["id"]): m for m in await repo.list_materials()}
    assigned = {str(a["segment_id"]) for a in variant["assignments"]}
    views = []
    for photo in project["photos"]:
        key = str(photo["id"])
        if not photo["is_primary"] or not any(str(s["id"]) in assigned for s in segments_by_photo[key]):
            continue
        before, after = await render_photo(photo, variant, measured, materials, storage)
        kind = "Standard"
        path = photoreal_path(photo, variant_id, after)
        if path in await storage.signed_urls([path]):  # an AI render exists for exactly this design
            after, kind = await storage.get(path), "Photorealistic (AI)"
        views.append({"title": ELEVATION_NAMES.get(photo["elevation"], photo["elevation"]),
                      "scale": scales[key].detail, "before": before, "after": after, "after_kind": kind})

    pdf = await run_in_threadpool(
        build_report, project["name"], estimate.model_dump(), views, datetime.now(timezone.utc), METHOD_NOTES,
    )
    filename = re.sub(r"[^A-Za-z0-9]+", "-", f"{project['name']} {variant['name']}").strip("-") or "report"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"',
                             "Cache-Control": "private, no-store"})
