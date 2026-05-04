from __future__ import annotations

import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import JobStatus


LEASE_TTL_SECONDS = 300
MAX_RETRIES = 3


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
    base = min(60, 2 ** retry_count)
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


def worker_loop(engine: Engine, *, poll_interval_seconds: float = 1.0) -> None:
    worker_id = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4()}"

    while True:
        with Session(engine) as session:
            with session.begin():
                job = claim_next_job(session, worker_id=worker_id)

                if not job:
                    job = None
                else:
                    mark_job_succeeded(session, job_id=job.job_id)

        if not job:
            time.sleep(poll_interval_seconds)


def main() -> None:
    from app.db.session import create_app_engine

    engine = create_app_engine()
    worker_loop(engine)


if __name__ == "__main__":
    main()

