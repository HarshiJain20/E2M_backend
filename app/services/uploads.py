"""
Photo uploads shared by "new project" and "add photos": validate every file, then store them.

All photos in a request are checked before anything is saved, so a request either adds all
of its photos or none. Rejections list each unusable photo with guidance for that photo.
"""
import uuid

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.domain import ELEVATIONS
from app.services.images import ImageRejected, PreparedImage, prepare_upload
from app.services.storage import Storage, StorageError

ACCEPTED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def assign_elevations(requested: list[str], count: int, taken: set[str]) -> list[str]:
    """Use the requested elevation per photo, or the next side not yet covered."""
    result, used = [], set(taken)
    for index in range(count):
        wanted = requested[index] if index < len(requested) and requested[index] else None
        if wanted is not None and wanted not in ELEVATIONS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown side of the house: {wanted}.")
        side = wanted or next((e for e in ELEVATIONS[:-1] if e not in used), "other")
        used.add(side)
        result.append(side)
    return result


async def prepare_photos(files: list[UploadFile], settings: Settings) -> list[PreparedImage]:
    max_bytes = settings.storage.max_file_size_mb * 1024 * 1024
    prepared: list[PreparedImage] = []
    problems: list[dict] = []

    for index, upload in enumerate(files):
        name = upload.filename or f"Photo {index + 1}"
        if upload.content_type not in ACCEPTED_TYPES:
            problems.append({"index": index, "filename": name, "message": "Upload a JPG, PNG or WebP photo."})
            continue
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            problems.append({"index": index, "filename": name,
                             "message": f"The photo is larger than {settings.storage.max_file_size_mb} MB."})
            continue
        try:
            image = await run_in_threadpool(
                prepare_upload, data, settings.storage.working_image_max_side, settings.storage.thumbnail_max_side
            )
        except ImageRejected as exc:
            problems.append({"index": index, "filename": name, "message": str(exc)})
            continue
        if not image.usable:
            problems.append({"index": index, "filename": name,
                             "message": "This photo can't be used for measurement.",
                             "quality_report": image.quality_report})
            continue
        prepared.append(image)

    if problems:
        count = len(problems)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "images_unusable",
                "message": (
                    "This photo can't be used. Replace it and try again." if len(files) == 1
                    else f"{count} of {len(files)} photos can't be used. Replace or remove them and try again."
                ),
                "photos": problems,
            },
        )
    return prepared


async def store_photos(
    storage: Storage, user_id, project_id: str, images: list[PreparedImage], elevations: list[str]
) -> list[dict]:
    """Upload the files and return photo rows ready to insert (is_primary decided later)."""
    rows, written = [], []
    try:
        for image, elevation in zip(images, elevations):
            photo_id = str(uuid.uuid4())
            prefix = f"{user_id}/{project_id}/{photo_id}"  # storage policies require the user's own folder
            paths = {k: f"{prefix}/{k}.jpg" for k in ("original", "working", "thumbnail")}
            for key, data in (("original", image.original_jpeg), ("working", image.working_jpeg),
                              ("thumbnail", image.thumbnail_jpeg)):
                await storage.put(paths[key], data, "image/jpeg")
                written.append(paths[key])
            rows.append({
                "id": photo_id,
                "project_id": project_id,
                "elevation": elevation,
                "is_primary": False,
                "status": "uploaded",
                "original_image_path": paths["original"],
                "working_image_path": paths["working"],
                "thumbnail_path": paths["thumbnail"],
                "image_width": image.width,
                "image_height": image.height,
                "image_meta": image.meta,
                "quality_report": image.quality_report,
            })
    except StorageError as exc:
        try:
            await storage.delete(written)
        except StorageError:
            pass
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The photos could not be saved. Try again.") from exc
    return rows
