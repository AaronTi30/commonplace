from __future__ import annotations

import uuid

from sqlalchemy import text

from app.worker.worker import MAX_RETRIES


def _seed_source_and_work(db_session, *, source_type: str = "gutenberg", locator: str = "1342") -> uuid.UUID:
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO sources (id, source_type, locator, canonical_url)
            VALUES (:id, :source_type, :locator, :url)
            """
        ),
        {
            "id": source_id,
            "source_type": source_type,
            "locator": locator,
            "url": f"https://example.com/{locator}",
        },
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
    return work_id


def _seed_job(db_session, *, work_id: uuid.UUID, status: str, retry_count: int = 0) -> uuid.UUID:
    job_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO ingestion_jobs (id, job_type, status, retry_count, work_id, payload)
            VALUES (:id, 'ingest_work', :status, :retry_count, :work_id, '{}'::jsonb)
            """
        ),
        {"id": job_id, "status": status, "retry_count": retry_count, "work_id": work_id},
    )
    return job_id


def test_ingest_active_job_reused_202(client, db_session):
    work_id = _seed_source_and_work(db_session)
    job_id = _seed_job(db_session, work_id=work_id, status="queued")

    resp = client.post("/api/ingest", json={"source_type": "gutenberg", "locator": "1342"})
    assert resp.status_code == 202
    assert resp.json()["work_id"] == str(work_id)
    assert resp.json()["job_id"] == str(job_id)


def test_ingest_complete_is_noop_200(client, db_session):
    work_id = _seed_source_and_work(db_session)
    db_session.execute(text("UPDATE works SET ingestion_state = 'complete' WHERE id = :id"), {"id": work_id})

    resp = client.post("/api/ingest", json={"source_type": "gutenberg", "locator": "1342"})
    assert resp.status_code == 200
    assert resp.json()["work_id"] == str(work_id)
    assert resp.json()["job_id"] is None


def test_ingest_terminal_failed_creates_new_job_202(client, db_session):
    work_id = _seed_source_and_work(db_session)
    db_session.execute(text("UPDATE works SET ingestion_state = 'failed' WHERE id = :id"), {"id": work_id})
    _seed_job(db_session, work_id=work_id, status="failed", retry_count=MAX_RETRIES)

    resp = client.post("/api/ingest", json={"source_type": "gutenberg", "locator": "1342"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["work_id"] == str(work_id)
    assert body["job_id"] is not None

    n = db_session.execute(
        text("SELECT COUNT(*) FROM ingestion_jobs WHERE work_id = :w"), {"w": work_id}
    ).scalar()
    assert int(n) == 2


def test_ingest_failed_but_already_queued_returns_existing_202(client, db_session):
    work_id = _seed_source_and_work(db_session)
    db_session.execute(text("UPDATE works SET ingestion_state = 'failed' WHERE id = :id"), {"id": work_id})
    job_id = _seed_job(db_session, work_id=work_id, status="queued", retry_count=1)

    resp = client.post("/api/ingest", json={"source_type": "gutenberg", "locator": "1342"})
    assert resp.status_code == 202
    assert resp.json()["job_id"] == str(job_id)

