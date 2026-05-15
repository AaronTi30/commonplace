from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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
    SourceArtifact,
    SourceType,
    Work,
)
from app.ingest.canonicalize import canonicalize_gutenberg, canonicalize_wikisource
from app.settings import settings
from app.worker.worker import MAX_RETRIES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingest"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


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


def _enqueue_ingest_job_if_needed(session: Session, *, work_id: uuid.UUID) -> tuple[IngestResponse, int]:
    work = session.get(Work, work_id)
    if work is None:
        raise RuntimeError("work missing")
    job = _latest_job(session, work_id=work_id)

    if job and job.status in {JobStatus.queued, JobStatus.running}:
        return (IngestResponse(work_id=work_id, job_id=job.id), status.HTTP_202_ACCEPTED)

    if work.ingestion_state == IngestionState.complete:
        return (IngestResponse(work_id=work_id, job_id=None), status.HTTP_200_OK)

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
        return (IngestResponse(work_id=work_id, job_id=new_job.id), status.HTTP_202_ACCEPTED)

    if work.ingestion_state == IngestionState.failed and job and job.status == JobStatus.queued:
        return (IngestResponse(work_id=work_id, job_id=job.id), status.HTTP_202_ACCEPTED)

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
    return (IngestResponse(work_id=work_id, job_id=new_job.id), status.HTTP_202_ACCEPTED)


def _ingest_json_response(resp: IngestResponse, code: int) -> IngestResponse | JSONResponse:
    if code == status.HTTP_202_ACCEPTED:
        return JSONResponse(status_code=code, content=jsonable_encoder(resp))
    return resp


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest, session: Session = Depends(get_db_session)) -> IngestResponse | JSONResponse:
    if req.source_type in {SourceType.epub, SourceType.pdf}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_locator", "use POST /api/ingest/upload for epub and pdf files"),
        )
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

    resp, code = _enqueue_ingest_job_if_needed(session, work_id=work_id)
    return _ingest_json_response(resp, code)


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    session: Session = Depends(get_db_session),
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    language: str | None = Form(None),
) -> IngestResponse | JSONResponse:
    raw_name = file.filename or "upload.bin"
    safe_base = os.path.basename(raw_name)
    ext = os.path.splitext(safe_base)[1].lower()
    if ext not in {".epub", ".pdf"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_file", "file extension must be .epub or .pdf"),
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        buf = await file.read(1024 * 1024)
        if not buf:
            break
        total += len(buf)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error("invalid_file", "file exceeds 100MB limit"),
            )
        chunks.append(buf)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_file", "empty file"),
        )

    digest = hashlib.sha256(data).hexdigest()
    source_type = SourceType.epub if ext == ".epub" else SourceType.pdf
    canonical_url = f"file://{safe_base}"

    source_id = _upsert_source(
        session,
        source_type=source_type,
        locator=digest,
        canonical_url=canonical_url,
    )
    work_id = _upsert_work(session, source_id=source_id)
    work = session.get(Work, work_id)
    if work is None:
        raise RuntimeError("work missing")

    for form_val, attr in ((title, "title"), (author, "author"), (language, "language")):
        if form_val is not None:
            stripped = form_val.strip()
            if stripped:
                setattr(work, attr, stripped)

    session.flush()

    job = _latest_job(session, work_id=work_id)
    skip_disk = work.ingestion_state == IngestionState.complete or (
        job is not None and job.status in {JobStatus.queued, JobStatus.running}
    )

    if not skip_disk:
        upload_root = settings.resolved_upload_dir()
        try:
            os.makedirs(upload_root, exist_ok=True)
        except OSError as exc:
            logger.exception("upload_dir not writable: %s", upload_root)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error("server_error", "upload storage is not available"),
            ) from exc

        dest_dir = os.path.join(upload_root, str(source_id))
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as exc:
            logger.exception("could not create upload subdirectory: %s", dest_dir)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error("server_error", "upload storage is not available"),
            ) from exc

        dest_path = os.path.join(dest_dir, safe_base)
        try:
            with open(dest_path, "wb") as out:
                out.write(data)
        except OSError as exc:
            logger.exception("could not write upload to %s", dest_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error("server_error", "upload storage is not available"),
            ) from exc

        session.add(
            SourceArtifact(
                id=uuid.uuid4(),
                source_id=source_id,
                retrieved_at=datetime.now(timezone.utc),
                retrieval_url=canonical_url,
                final_url=canonical_url,
                http_status=200,
                content_type=file.content_type,
                content_sha256=digest,
                raw_text=None,
                raw_html=None,
                raw_file_path=dest_path,
                parser_version="upload-1",
            )
        )
        session.flush()

    resp, code = _enqueue_ingest_job_if_needed(session, work_id=work_id)
    return _ingest_json_response(resp, code)
