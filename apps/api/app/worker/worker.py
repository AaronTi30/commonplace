from __future__ import annotations

import hashlib
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Passage,
    ProgressStage,
    SourceArtifact,
    SourceType,
    Work,
    update_ingestion_job_progress,
)
from app.ingest.chunk import CHUNKER_VERSION, chunk_normalized_text
from app.ingest.embed import EMBEDDING_DIM, EMBEDDING_MODEL, embed_passages_for_work
from app.ingest.extract_epub import extract_epub_metadata, extract_epub_text
from app.ingest.extract_pdf import extract_pdf_metadata, extract_pdf_text
from app.ingest.fetch_gutenberg import ArtifactFetchResult, fetch_gutenberg
from app.ingest.fetch_wikisource import fetch_wikisource
from app.ingest.metadata import WorkMetadata, extract_gutenberg_metadata, extract_wikisource_metadata, fetch_gutenberg_metadata_api
from app.ingest.normalize import normalized_plaintext_for_chunking

LEASE_TTL_SECONDS = 300
MAX_RETRIES = 3

PARSER_VERSION_FETCH = "fetch-mvp-1"


@dataclass(frozen=True)
class ClaimedJob:
    job_id: uuid.UUID
    work_id: uuid.UUID
    status: str
    retry_count: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def claim_next_job(session: Session, *, worker_id: str) -> ClaimedJob | None:
    """
    Claim the oldest eligible job (queued or expired-running) and set a lease.

    Must be called inside a transaction.
    """
    row = session.execute(
        text(
            """
            SELECT id
            FROM ingestion_jobs
            WHERE
              available_at <= now()
              AND (
                status = 'queued'
                OR (status = 'running' AND lock_expires_at < now())
              )
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )
    ).fetchone()

    if not row:
        return None

    job_id = row[0]
    lease_expires = _utcnow() + timedelta(seconds=LEASE_TTL_SECONDS)

    updated = session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET
              status = 'running',
              locked_by = :worker_id,
              locked_at = now(),
              lock_expires_at = :lease_expires,
              updated_at = now()
            WHERE id = :job_id
            RETURNING id, work_id, status, retry_count
            """
        ),
        {"job_id": job_id, "worker_id": worker_id, "lease_expires": lease_expires},
    ).fetchone()

    if not updated:
        return None

    session.execute(
        text(
            """
            UPDATE works
            SET ingestion_state = 'running', updated_at = now()
            WHERE id = :work_id
            """
        ),
        {"work_id": updated.work_id},
    )

    return ClaimedJob(
        job_id=updated.id,
        work_id=updated.work_id,
        status=updated.status,
        retry_count=updated.retry_count,
    )


def mark_job_succeeded(session: Session, *, job_id: uuid.UUID) -> None:
    row = session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET
              status = 'succeeded',
              error = NULL,
              locked_by = NULL,
              locked_at = NULL,
              lock_expires_at = NULL,
              updated_at = now()
            WHERE id = :job_id
            RETURNING work_id
            """
        ),
        {"job_id": job_id},
    ).fetchone()
    if not row:
        return

    session.execute(
        text(
            """
            UPDATE works
            SET ingestion_state = 'complete', ingested_at = now(), updated_at = now()
            WHERE id = :work_id
            """
        ),
        {"work_id": row.work_id},
    )


def _retry_backoff_seconds(retry_count: int) -> int:
    base = min(60, 2**retry_count)
    return max(1, base) + random.randint(0, 3)


def mark_job_failed(session: Session, *, job_id: uuid.UUID, error: str) -> None:
    """
    Increment retry_count; queue with backoff if under MAX_RETRIES, else terminal-fail.
    """
    current = session.execute(
        text("SELECT retry_count, work_id FROM ingestion_jobs WHERE id = :job_id FOR UPDATE"),
        {"job_id": job_id},
    ).fetchone()
    if not current:
        return

    next_retry = int(current.retry_count) + 1

    if next_retry < MAX_RETRIES:
        delay = _retry_backoff_seconds(next_retry)
        available_at = _utcnow() + timedelta(seconds=delay)
        session.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET
                  status = 'queued',
                  retry_count = :retry_count,
                  error = :error,
                  locked_by = NULL,
                  locked_at = NULL,
                  lock_expires_at = NULL,
                  available_at = :available_at,
                  updated_at = now()
                WHERE id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "retry_count": next_retry,
                "error": error,
                "available_at": available_at,
            },
        )
    else:
        session.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET
                  status = 'failed',
                  retry_count = :retry_count,
                  error = :error,
                  locked_by = NULL,
                  locked_at = NULL,
                  lock_expires_at = NULL,
                  updated_at = now()
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id, "retry_count": next_retry, "error": error},
        )

    session.execute(
        text(
            """
            UPDATE works
            SET ingestion_state = 'failed', updated_at = now()
            WHERE id = :work_id
            """
        ),
        {"work_id": current.work_id},
    )


def _latest_ok_artifact(session: Session, *, source_id: uuid.UUID) -> SourceArtifact | None:
    return session.scalar(
        select(SourceArtifact)
        .where(SourceArtifact.source_id == source_id)
        .where(SourceArtifact.http_status >= 200)
        .where(SourceArtifact.http_status < 300)
        .order_by(SourceArtifact.created_at.desc())
        .limit(1)
    )


def _artifact_body_bytes(res: ArtifactFetchResult) -> bytes:
    if res.raw_text is not None:
        return res.raw_text.encode("utf-8")
    if res.raw_html is not None:
        return res.raw_html.encode("utf-8")
    raise RuntimeError("artifact fetch result has no raw body")


def _fetch_and_store_artifact(session: Session, *, work: Work, source_type: SourceType) -> SourceArtifact:
    source = work.source
    if source is None:
        raise RuntimeError("work missing source")

    if source_type == SourceType.gutenberg:
        res = fetch_gutenberg(source.locator)
    elif source_type == SourceType.wikisource:
        res = fetch_wikisource(source.locator)
    else:
        raise RuntimeError(f"unsupported source_type {source_type!r}")

    if not res.ok_for_source_artifact_row():
        raise RuntimeError(f"upstream fetch failed with HTTP {res.http_status}")

    body = _artifact_body_bytes(res)
    artifact = SourceArtifact(
        id=uuid.uuid4(),
        source_id=source.id,
        retrieved_at=_utcnow(),
        retrieval_url=res.retrieval_url,
        final_url=res.final_url,
        http_status=res.http_status,
        content_type=res.content_type,
        content_sha256=hashlib.sha256(body).hexdigest(),
        raw_text=res.raw_text,
        raw_html=res.raw_html,
        parser_version=PARSER_VERSION_FETCH,
    )
    session.add(artifact)
    session.flush()
    return artifact


def _load_raw_from_artifact(artifact: SourceArtifact) -> str:
    if artifact.raw_text is not None:
        return artifact.raw_text
    if artifact.raw_html is not None:
        return artifact.raw_html
    raise RuntimeError("artifact has no raw payload")


def run_ingest_job(session: Session, job_id: uuid.UUID, work_id: uuid.UUID) -> None:
    """
    Ingestion pipeline: fetch → normalize (in-memory) → chunk → embed → upsert bookkeeping.

    Expects ``work`` rows and ``ingestion_jobs`` row to exist. Commits are the caller's
    responsibility (run inside ``session.begin()``).
    """
    work = session.execute(
        select(Work).where(Work.id == work_id).options(joinedload(Work.source))
    ).unique().scalar_one()
    source = work.source
    if source is None:
        raise RuntimeError("work has no source")

    source_type = source.source_type

    update_ingestion_job_progress(session, job_id, ProgressStage.fetch, fetched=0)
    artifact = _latest_ok_artifact(session, source_id=source.id)
    if artifact is None:
        if source_type in (SourceType.epub, SourceType.pdf):
            raise RuntimeError(
                "missing uploaded file for this work; use POST /api/ingest/upload for epub and pdf"
            )
        artifact = _fetch_and_store_artifact(session, work=work, source_type=source_type)
    update_ingestion_job_progress(session, job_id, ProgressStage.fetch, fetched=1)

    update_ingestion_job_progress(session, job_id, ProgressStage.normalize)
    if source_type == SourceType.epub:
        path = artifact.raw_file_path
        if not path:
            raise RuntimeError("epub artifact has no raw_file_path")
        if not os.path.isfile(path):
            raise RuntimeError(f"file not found at {path}")
        try:
            normalized = extract_epub_text(path)
        except Exception as exc:
            raise RuntimeError(f"EPUB parse failed: {exc!r}") from exc
    elif source_type == SourceType.pdf:
        path = artifact.raw_file_path
        if not path:
            raise RuntimeError("pdf artifact has no raw_file_path")
        if not os.path.isfile(path):
            raise RuntimeError(f"file not found at {path}")
        try:
            normalized = extract_pdf_text(path)
        except Exception as exc:
            raise RuntimeError(f"PDF parse failed: {exc!r}") from exc
    else:
        raw = _load_raw_from_artifact(artifact)
        normalized = normalized_plaintext_for_chunking(raw, source_type.value)

    # Best-effort metadata extraction (improves UI + citation strings).
    if source_type == SourceType.gutenberg:
        # Try the Gutendex API first (works for all Gutenberg books regardless of format),
        # fall back to parsing the raw text header (works for modern-format files).
        md = fetch_gutenberg_metadata_api(source.locator)
        if not (md.title and md.author):
            md_text = extract_gutenberg_metadata(artifact.raw_text) if artifact.raw_text else WorkMetadata()
            md = WorkMetadata(
                title=md.title or md_text.title,
                author=md.author or md_text.author,
                language=md.language or md_text.language,
            )
    elif source_type == SourceType.wikisource and artifact.raw_html is not None:
        md = extract_wikisource_metadata(canonical_locator=source.locator, raw_html=artifact.raw_html)
    elif source_type == SourceType.epub and artifact.raw_file_path:
        try:
            md = extract_epub_metadata(artifact.raw_file_path)
        except Exception:
            md = None
    elif source_type == SourceType.pdf and artifact.raw_file_path:
        try:
            md = extract_pdf_metadata(artifact.raw_file_path)
        except Exception:
            md = None
    else:
        md = None

    if md is not None:
        if md.title and not work.title:
            work.title = md.title
        if md.author and not work.author:
            work.author = md.author
        if md.language and not work.language:
            work.language = md.language

    update_ingestion_job_progress(session, job_id, ProgressStage.chunk)
    chunks = chunk_normalized_text(
        normalized,
        author=work.author,
        title=work.title,
        chunker_version=CHUNKER_VERSION,
    )
    session.execute(delete(Passage).where(Passage.work_id == work_id))
    for ch in chunks:
        session.add(
            Passage(
                id=uuid.uuid4(),
                work_id=work_id,
                section_label=ch.section_label,
                passage_index=ch.passage_index,
                raw_text=ch.cleaned_text,
                cleaned_text=ch.cleaned_text,
                citation_string=ch.citation_string,
                chunker_version=ch.chunker_version,
            )
        )
    session.flush()
    total = len(chunks)
    update_ingestion_job_progress(
        session,
        job_id,
        ProgressStage.chunk,
        chunked=total,
        total_passages=total,
    )

    update_ingestion_job_progress(session, job_id, ProgressStage.embed, embedded=0)
    embedded = embed_passages_for_work(session, work_id)
    session.flush()
    update_ingestion_job_progress(
        session,
        job_id,
        ProgressStage.embed,
        embedded=embedded,
        total_passages=total,
    )

    update_ingestion_job_progress(
        session,
        job_id,
        ProgressStage.upsert,
        upserted=total,
        total_passages=total,
    )


def worker_loop(engine: Engine, *, poll_interval_seconds: float = 1.0) -> None:
    worker_id = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4()}"

    while True:
        job: ClaimedJob | None = None
        with Session(engine) as session:
            with session.begin():
                job = claim_next_job(session, worker_id=worker_id)

        if not job:
            time.sleep(poll_interval_seconds)
            continue

        try:
            with Session(engine) as session:
                with session.begin():
                    run_ingest_job(session, job.job_id, job.work_id)
            with Session(engine) as session:
                with session.begin():
                    mark_job_succeeded(session, job_id=job.job_id)
        except Exception as exc:  # noqa: BLE001 — surface last error to job row
            with Session(engine) as session:
                with session.begin():
                    mark_job_failed(session, job_id=job.job_id, error=repr(exc))


def main() -> None:
    from app.db.session import create_app_engine

    engine = create_app_engine()
    worker_loop(engine)


if __name__ == "__main__":
    main()
