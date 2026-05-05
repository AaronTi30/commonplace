from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.errors import error
from app.db.deps import get_db_session
from app.db.models import IngestionJob

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, session: Session = Depends(get_db_session)) -> dict:
    job = session.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "job not found"))

    progress = dict(job.progress or {})
    progress.setdefault("stage", job.progress_stage.value)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "progress": progress,
        "error": job.error,
        "retry_count": job.retry_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }

