"""
Background analysis jobs — one per photo.

A job loads the photo's working image, sends it to the ai-geometry service, and stores the
detected segments. It runs as the user who started it (their repository and storage), so
Row Level Security applies to the job's writes too. Progress is written to the job row so
the frontend can poll it.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.domain import JobStatus, ProjectStatus
from app.repositories.base import Repository
from app.services import ai_geometry
from app.services.storage import Storage

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "The analysis was interrupted before it finished. Run it again."
# A job that is not running in this process and has not progressed for this long is treated
# as interrupted (for example by a server restart).
STALE_AFTER = timedelta(minutes=2)

RUNNING_JOBS: set[str] = set()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _segment_row(photo: dict, item: dict) -> dict:
    return {
        "project_id": str(photo["project_id"]),
        "photo_id": str(photo["id"]),
        "label": item["label"],
        "source": "auto",
        "confidence": item.get("confidence"),
        "polygon": item["polygon"],
        "bbox": item["bbox"],
        "measure_type": item.get("measure_type", "area"),
        "area_sqm": item.get("area_sqm"),
        "length_m": item.get("length_m"),
        "scale_source": item.get("scale_source"),
        "depth_stats": {"median_m": item["depth_m"]} if item.get("depth_m") else None,
    }


async def start_analysis(photo: dict, repo: Repository) -> dict:
    """Create the job row and mark the photo as processing; the caller schedules run_analysis."""
    job = await repo.create_job({
        "project_id": str(photo["project_id"]), "photo_id": str(photo["id"]),
        "kind": "analyze", "status": JobStatus.QUEUED, "stage": "Queued",
    })
    await repo.update_photo(str(photo["id"]), {"status": ProjectStatus.PROCESSING})
    return job


async def run_analysis(job_id: str, photo: dict, repo: Repository, storage: Storage) -> None:
    photo_id = str(photo["id"])
    RUNNING_JOBS.add(job_id)
    try:
        await repo.update_job(job_id, {
            "status": JobStatus.RUNNING, "started_at": utcnow_iso(), "stage": "Preparing image", "progress": 10,
        })
        image = await storage.get(photo["working_image_path"])

        await repo.update_job(job_id, {"stage": "Detecting surfaces and measuring", "progress": 30})
        result = await ai_geometry.analyze_image(image)

        await repo.update_job(job_id, {"stage": "Saving results", "progress": 85})
        await repo.replace_auto_segments(photo_id, [_segment_row(photo, s) for s in result["segments"]])

        await repo.update_job(job_id, {
            "status": JobStatus.SUCCEEDED,
            "stage": "Complete",
            "progress": 100,
            "finished_at": utcnow_iso(),
            "result_meta": {
                "mock": result.get("mock", False),
                "camera": result.get("camera"),
                "depth": result.get("depth"),
                "timings_ms": result.get("timings_ms"),
                "models": result.get("models"),
                "warnings": result.get("warnings", []),
                "segment_count": len(result["segments"]),
            },
        })
        camera = result.get("camera") or {}
        # New regions replace the old ones, so any reference measurement on them is dropped.
        await repo.update_photo(photo_id, {
            "status": ProjectStatus.REVIEW,
            "measurement": {"focal_length_px": camera.get("focal_length_px"), "focal_source": camera.get("source")},
        })
    except Exception as exc:  # any failure must end the job, never leave it running
        logger.exception("Analysis job %s failed", job_id)
        message = str(exc) if isinstance(exc, ai_geometry.AIGeometryError) else (
            "Something went wrong while analysing the photo. Try again."
        )
        try:
            await repo.update_job(job_id, {
                "status": JobStatus.FAILED, "error": message, "finished_at": utcnow_iso(),
            })
            await repo.update_photo(photo_id, {"status": ProjectStatus.FAILED})
        except Exception:
            logger.exception("Could not record failure of job %s", job_id)
    finally:
        RUNNING_JOBS.discard(job_id)


def _as_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_interrupted(job: dict | None, now: datetime | None = None) -> bool:
    if not job or job["status"] not in JobStatus.ACTIVE or str(job["id"]) in RUNNING_JOBS:
        return False
    last_activity = _as_datetime(job.get("started_at") or job["created_at"])
    return (now or datetime.now(timezone.utc)) - last_activity > STALE_AFTER


async def recover_interrupted(project: dict, repo: Repository) -> dict:
    """Mark photos whose latest job stopped without finishing as failed."""
    photos = []
    for photo in project["photos"]:
        job = photo.get("latest_job")
        if is_interrupted(job):
            job = await repo.update_job(str(job["id"]), {
                "status": JobStatus.FAILED, "error": INTERRUPTED_MESSAGE, "finished_at": utcnow_iso(),
            }) or job
            await repo.update_photo(str(photo["id"]), {"status": ProjectStatus.FAILED})
            photo = {**photo, "latest_job": job, "status": ProjectStatus.FAILED}
        photos.append(photo)
    return {**project, "photos": photos}
