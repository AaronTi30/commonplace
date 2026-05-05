from __future__ import annotations

import uuid

from sqlalchemy import text


def test_get_job_404(client):
    resp = client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_get_job_returns_shape(client, db_session):
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    job_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO sources (id, source_type, locator, canonical_url) VALUES (:id,'gutenberg',:l,:u)"
        ),
        {"id": source_id, "l": "1", "u": "https://example.com"},
    )
    db_session.execute(
        text("INSERT INTO works (id, source_id, ingestion_state) VALUES (:id,:s,'queued')"),
        {"id": work_id, "s": source_id},
    )
    db_session.execute(
        text(
            "INSERT INTO ingestion_jobs (id, job_type, status, work_id, payload) VALUES (:id,'ingest_work','queued',:w,'{}'::jsonb)"
        ),
        {"id": job_id, "w": work_id},
    )

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["status"] == "queued"
    assert body["progress"]["stage"] == "fetch"

