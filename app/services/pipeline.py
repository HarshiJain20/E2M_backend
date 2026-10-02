"""
Background analysis jobs.

A job loads the project's working image, sends it to the ai-geometry service, and
stores the detected segments. Progress is written to the `jobs` row so the frontend
can poll it. Jobs run in-process; a server restart marks unfinished jobs as failed.
"""
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.models import Job, JobStatus, Project, ProjectStatus, Segment, utcnow
from app.services import ai_geometry
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

INTERRUPTED_MESSAGE = "The analysis was interrupted by a server restart. Run it again."


async def _set_stage(session: AsyncSession, job: Job, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = progress
    await session.commit()


def _segment_from_result(project_id: uuid.UUID, item: dict) -> Segment:
    return Segment(
        project_id=project_id,
        label=item["label"],
        source="auto",
        confidence=item.get("confidence"),
        polygon=item["polygon"],
        bbox=item["bbox"],
        measure_type=item.get("measure_type", "area"),
        area_sqm=item.get("area_sqm"),
        length_m=item.get("length_m"),
        scale_source=item.get("scale_source"),
        depth_stats=item.get("depth_stats"),
    )


async def run_analysis(job_id: uuid.UUID, session_factory: SessionFactory = AsyncSessionLocal) -> None:
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        project = await session.get(Project, job.project_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        project.status = ProjectStatus.PROCESSING
        await _set_stage(session, job, "Preparing image", 10)

        try:
            image = await get_storage().get(project.working_image_path)
            await _set_stage(session, job, "Detecting surfaces and measuring", 30)
            result = await ai_geometry.analyze_image(image)

            await _set_stage(session, job, "Saving results", 85)
            await session.execute(
                delete(Segment).where(Segment.project_id == project.id, Segment.source == "auto")
            )
            session.add_all(_segment_from_result(project.id, item) for item in result["segments"])

            job.result_meta = {
                "mock": result.get("mock", False),
                "camera": result.get("camera"),
                "depth": result.get("depth"),
                "timings_ms": result.get("timings_ms"),
                "models": result.get("models"),
                "segment_count": len(result["segments"]),
            }
            job.status = JobStatus.SUCCEEDED
            job.stage = "Complete"
            job.progress = 100
            job.finished_at = utcnow()
            project.status = ProjectStatus.REVIEW
            await session.commit()
        except Exception as exc:  # any failure must end the job, never leave it running
            logger.exception("Analysis job %s failed", job_id)
            await session.rollback()
            job = await session.get(Job, job_id)
            project = await session.get(Project, job.project_id)
            job.status = JobStatus.FAILED
            job.error = str(exc) if isinstance(exc, ai_geometry.AIGeometryError) else (
                "Something went wrong while analysing the photo. Try again."
            )
            job.finished_at = utcnow()
            project.status = ProjectStatus.FAILED
            await session.commit()


async def fail_interrupted_jobs(session_factory: SessionFactory = AsyncSessionLocal) -> int:
    """Mark jobs left queued/running by a previous process as failed."""
    async with session_factory() as session:
        result = await session.execute(
            update(Job)
            .where(Job.status.in_(JobStatus.ACTIVE))
            .values(status=JobStatus.FAILED, error=INTERRUPTED_MESSAGE, finished_at=utcnow())
        )
        await session.execute(
            update(Project)
            .where(Project.status == ProjectStatus.PROCESSING)
            .values(status=ProjectStatus.FAILED)
        )
        await session.commit()
        return result.rowcount or 0
