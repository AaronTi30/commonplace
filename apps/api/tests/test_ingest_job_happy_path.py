from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import delete, select, text

from app.db.models import (
    IngestionJob,
    IngestionState,
    JobStatus,
    JobType,
    Passage,
    ProgressStage,
    Source,
    SourceArtifact,
    SourceType,
    Work,
)
from app.ingest.embed import EMBEDDING_DIM
from app.ingest.fetch_gutenberg import ArtifactFetchResult
from app.worker.worker import run_ingest_job


def _seed_ingest(db_session, *, locator: str = "42") -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    job_id = uuid.uuid4()
    db_session.add(
        Source(
            id=source_id,
            source_type=SourceType.gutenberg,
            locator=locator,
            canonical_url=f"https://www.gutenberg.org/ebooks/{locator}",
        )
    )
    db_session.add(
        Work(
            id=work_id,
            source_id=source_id,
            title=None,
            author=None,
            ingestion_state=IngestionState.running,
        )
    )
    db_session.add(
        IngestionJob(
            id=job_id,
            job_type=JobType.ingest_work,
            status=JobStatus.running,
            work_id=work_id,
            payload={},
        )
    )
    db_session.flush()
    return work_id, job_id, source_id


def _fake_fetch(body: str):
    def _inner(locator_id: str, *, client=None, timeout: float = 60.0) -> ArtifactFetchResult:
        _ = locator_id
        b = body.encode("utf-8")
        return ArtifactFetchResult(
            raw_text=body,
            raw_html=None,
            retrieval_url="https://www.gutenberg.org/files/0/0-0.txt",
            final_url="https://www.gutenberg.org/files/0/0-0.txt",
            http_status=200,
            content_type="text/plain; charset=utf-8",
            content_sha256=hashlib.sha256(b).hexdigest(),
        )

    return _inner


def test_run_ingest_job_fetch_chunk_embed_progress(monkeypatch, db_session):
    work_id, job_id, _ = _seed_ingest(db_session)
    body = (
        "Title: Demo Title\n"
        "Author: Demo Author\n"
        "Language: English\n"
        "\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK DEMO ***\n"
        "First chunk of prose here.\n\nSecond chunk follows with different words.\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK DEMO ***\n"
    )
    monkeypatch.setattr("app.worker.worker.fetch_gutenberg", _fake_fetch(body))

    def fake_encode(texts: list[str]) -> list[list[float]]:
        return [[0.001] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.ingest.embed.encode_texts", fake_encode)

    run_ingest_job(db_session, job_id, work_id)
    db_session.flush()

    work = db_session.get(Work, work_id)
    assert work is not None
    assert work.title == "Demo Title"
    assert work.author == "Demo Author"
    assert work.language == "English"

    job = db_session.get(IngestionJob, job_id)
    assert job is not None
    assert job.progress_stage == ProgressStage.upsert
    assert job.progress.get("stage") == "upsert"
    assert job.progress.get("total_passages", 0) >= 1

    passages = db_session.scalars(select(Passage).where(Passage.work_id == work_id)).all()
    assert len(passages) >= 1
    emb_rows = db_session.execute(
        text("SELECT COUNT(*) FROM passage_embeddings WHERE work_id = :w"), {"w": work_id}
    ).scalar()
    assert emb_rows == len(passages)


def test_reingest_removes_old_passage_ids(monkeypatch, db_session):
    work_id, job_id, source_id = _seed_ingest(db_session, locator="99")

    def fake_encode(texts: list[str]) -> list[list[float]]:
        return [[0.003] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.ingest.embed.encode_texts", fake_encode)

    body_a = ("x" * 900 + "\n\n" + "y" * 900 + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK A ***\n")
    monkeypatch.setattr("app.worker.worker.fetch_gutenberg", _fake_fetch(body_a))
    run_ingest_job(db_session, job_id, work_id)
    db_session.flush()
    ids_a = {p.id for p in db_session.scalars(select(Passage).where(Passage.work_id == work_id)).all()}

    db_session.execute(delete(SourceArtifact).where(SourceArtifact.source_id == source_id))
    db_session.flush()

    body_b = ("z" * 1200 + "\n\n" + "w" * 1200 + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK B ***\n")
    monkeypatch.setattr("app.worker.worker.fetch_gutenberg", _fake_fetch(body_b))
    run_ingest_job(db_session, job_id, work_id)
    db_session.flush()
    ids_b = {p.id for p in db_session.scalars(select(Passage).where(Passage.work_id == work_id)).all()}

    assert ids_a.isdisjoint(ids_b)
    assert len(ids_b) >= 1
