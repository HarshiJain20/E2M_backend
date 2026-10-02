"""Job status polling."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_repository
from app.repositories.base import Repository
from app.schemas.project import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, repo: Repository = Depends(get_repository)) -> JobOut:
    job = await repo.get_job(str(job_id))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return JobOut(**job)
