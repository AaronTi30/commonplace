from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.errors import error
from app.db.deps import get_db_session
from app.db.models import (
    IngestionJob,
    IngestionState,
    JobStatus,
    JobType,
    Source,
    SourceType,
    Work,
)
from app.ingest.canonicalize import canonicalize_gutenberg, canonicalize_wikisource
from app.worker.worker import MAX_RETRIES

router = APIRouter(prefix="/api", tags=["ingest"])


class IngestRequest(BaseModel):
    source_type: SourceType
    locator: str


class IngestResponse(BaseModel):
    work_id: uuid.UUID
    job_id: uuid.UUID | None


def _canonicalize(req: IngestRequest) -> tuple[str, str]:
    if req.source_type == SourceType.gutenberg:
        c = canonicalize_gutenberg(req.locator)
        return c.locator, c.canonical_url
    if req.source_type == SourceType.wikisource:
        c = canonicalize_wikisource(req.locator)
        return c.locator, c.canonical_url
    raise ValueError(f"unsupported source_type: {req.source_type}")


def _upsert_source(session: Session, *, source_type: SourceType, locator: str, canonical_url: str) -> uuid.UUID:
    stmt = (
        pg_insert(Source)
        .values(
            id=uuid.uuid4(),
            source_type=source_type,
            locator=locator,
            canonical_url=canonical_url,
        )
        .on_conflict_do_update(
            constraint="uq_sources_type_locator",
            set_={"canonical_url": canonical_url},
        )
        .returning(Source.id)
    )
    return session.execute(stmt).scalar_one()


def _upsert_work(session: Session, *, source_id: uuid.UUID) -> uuid.UUID:
    stmt = (
        pg_insert(Work)
        .values(id=uuid.uuid4(), source_id=source_id, ingestion_state=IngestionState.queued)
        .on_conflict_do_nothing(constraint="uq_works_source_id")
        .returning(Work.id)
    )
    work_id = session.execute(stmt).scalar_one_or_none()
    if work_id is not None:
        return work_id
    return session.execute(select(Work.id).where(Work.source_id == source_id)).scalar_one()


def _latest_job(session: Session, *, work_id: uuid.UUID) -> IngestionJob | None:
    return session.scalar(
        select(IngestionJob).where(IngestionJob.work_id == work_id).order_by(IngestionJob.created_at.desc()).limit(1)
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, session: Session = Depends(get_db_session)) -> IngestResponse:
    try:
        locator, canonical_url = _canonicalize(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error("invalid_locator", str(e))) from e

    source_id = _upsert_source(
        session,
        source_type=req.source_type,
        locator=locator,
        canonical_url=canonical_url,
    )
    work_id = _upsert_work(session, source_id=source_id)

    work = session.get(Work, work_id)
    assert work is not None

    job = _latest_job(session, work_id=work_id)

    # If there is an active job, reuse it.
    if job and job.status in {JobStatus.queued, JobStatus.running}:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=jsonable_encoder(IngestResponse(work_id=work_id, job_id=job.id)),
        )

    # Work is already complete and no new job needed.
    if work.ingestion_state == IngestionState.complete:
        return IngestResponse(work_id=work_id, job_id=None)

    # If terminal failed, create a new job (user-triggered retry).
    if (
        work.ingestion_state == IngestionState.failed
        and job
        and job.status == JobStatus.failed
        and job.retry_count >= MAX_RETRIES
    ):
        new_job = IngestionJob(
            id=uuid.uuid4(),
            job_type=JobType.ingest_work,
            status=JobStatus.queued,
            retry_count=0,
            work_id=work_id,
            payload={},
        )
        session.add(new_job)
        work.ingestion_state = IngestionState.queued
        session.flush()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=jsonable_encoder(IngestResponse(work_id=work_id, job_id=new_job.id)),
        )

    # Non-terminal failed but already queued for retry: return latest job id.
    if work.ingestion_state == IngestionState.failed and job and job.status == JobStatus.queued:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=jsonable_encoder(IngestResponse(work_id=work_id, job_id=job.id)),
        )

    # Default: enqueue a new job.
    new_job = IngestionJob(
        id=uuid.uuid4(),
        job_type=JobType.ingest_work,
        status=JobStatus.queued,
        retry_count=0,
        work_id=work_id,
        payload={},
    )
    session.add(new_job)
    work.ingestion_state = IngestionState.queued
    session.flush()
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=jsonable_encoder(IngestResponse(work_id=work_id, job_id=new_job.id)),
    )

