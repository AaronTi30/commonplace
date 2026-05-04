import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.worker.worker import LEASE_TTL_SECONDS, claim_next_job, mark_job_failed


def _seed_work_and_job(db_session, *, status: str = "queued") -> tuple[uuid.UUID, uuid.UUID]:
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    job_id = uuid.uuid4()

    db_session.execute(
        text(
            """
            INSERT INTO sources (id, source_type, locator, canonical_url)
            VALUES (:id, 'gutenberg', :locator, :url)
            """
        ),
        {"id": source_id, "locator": str(uuid.uuid4()), "url": "https://example.com"},
    )
    db_session.execute(
        text(
            """
            INSERT INTO works (id, source_id, ingestion_state)
            VALUES (:id, :source_id, 'queued')
            """
        ),
        {"id": work_id, "source_id": source_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO ingestion_jobs (id, job_type, status, work_id, payload)
            VALUES (:id, 'ingest_work', :status, :work_id, '{}'::jsonb)
            """
        ),
        {"id": job_id, "status": status, "work_id": work_id},
    )
    return work_id, job_id


def test_claim_sets_lease_and_marks_work_running(db_session):
    work_id, job_id = _seed_work_and_job(db_session)

    with db_session.begin_nested():
        claimed = claim_next_job(db_session, worker_id="test-worker")

    assert claimed is not None
    assert claimed.job_id == job_id
    assert claimed.work_id == work_id

    row = db_session.execute(
        text(
            """
            SELECT status, locked_by, locked_at, lock_expires_at
            FROM ingestion_jobs
            WHERE id = :id
            """
        ),
        {"id": job_id},
    ).fetchone()

    assert row.status == "running"
    assert row.locked_by == "test-worker"
    assert row.locked_at is not None
    assert row.lock_expires_at is not None

    work = db_session.execute(
        text("SELECT ingestion_state FROM works WHERE id = :id"), {"id": work_id}
    ).fetchone()
    assert work.ingestion_state == "running"


def test_expired_running_job_can_be_reclaimed(db_session):
    work_id, job_id = _seed_work_and_job(db_session, status="running")

    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.execute(
        text(
            """
            UPDATE ingestion_jobs
            SET lock_expires_at = :expired, locked_by = 'dead-worker', locked_at = :expired
            WHERE id = :id
            """
        ),
        {"id": job_id, "expired": expired},
    )

    with db_session.begin_nested():
        claimed = claim_next_job(db_session, worker_id="new-worker")

    assert claimed is not None
    assert claimed.job_id == job_id

    row = db_session.execute(
        text("SELECT locked_by, lock_expires_at FROM ingestion_jobs WHERE id = :id"),
        {"id": job_id},
    ).fetchone()

    assert row.locked_by == "new-worker"
    assert row.lock_expires_at is not None


def test_failure_increments_retry_and_applies_backoff(db_session):
    work_id, job_id = _seed_work_and_job(db_session)

    with db_session.begin_nested():
        claimed = claim_next_job(db_session, worker_id="test-worker")
        assert claimed is not None
        mark_job_failed(db_session, job_id=job_id, error="boom")

    job = db_session.execute(
        text("SELECT status, retry_count, available_at FROM ingestion_jobs WHERE id = :id"),
        {"id": job_id},
    ).fetchone()

    assert job.retry_count == 1
    assert job.status == "queued"
    assert job.available_at is not None

    # Should not be immediately claimable due to backoff.
    with db_session.begin_nested():
        claimed2 = claim_next_job(db_session, worker_id="test-worker-2")
    assert claimed2 is None

    # Work transitions to failed on stage error.
    work = db_session.execute(
        text("SELECT ingestion_state FROM works WHERE id = :id"), {"id": work_id}
    ).fetchone()
    assert work.ingestion_state == "failed"

