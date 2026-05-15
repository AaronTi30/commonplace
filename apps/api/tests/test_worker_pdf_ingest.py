from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

import fitz
from sqlalchemy import select

from app.db.models import (
    IngestionJob,
    IngestionState,
    JobStatus,
    JobType,
    Passage,
    Source,
    SourceArtifact,
    SourceType,
    Work,
)
from app.ingest.embed import EMBEDDING_DIM
from app.worker.worker import run_ingest_job


def _write_minimal_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "worker pdf unique phrase plugh.")
        doc.set_metadata({"title": "Worker PDF Title", "author": "Worker PDF Author"})
        doc.save(str(path))
    finally:
        doc.close()


def test_run_ingest_job_pdf_from_artifact_file(monkeypatch, db_session, tmp_path):
    pdf_path = tmp_path / "seed.pdf"
    _write_minimal_pdf(pdf_path)
    data = pdf_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    upload_root = tmp_path / "uploads"
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    job_id = uuid.uuid4()

    dest_dir = upload_root / str(source_id)
    dest_dir.mkdir(parents=True)
    stored = dest_dir / "seed.pdf"
    shutil.copy(pdf_path, stored)

    db_session.add(
        Source(
            id=source_id,
            source_type=SourceType.pdf,
            locator=digest,
            canonical_url="file://seed.pdf",
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
    db_session.add(
        SourceArtifact(
            id=uuid.uuid4(),
            source_id=source_id,
            http_status=200,
            content_sha256=digest,
            raw_file_path=str(stored),
            retrieval_url="file://seed.pdf",
            final_url="file://seed.pdf",
        )
    )
    db_session.flush()

    def fake_encode(texts: list[str]) -> list[list[float]]:
        return [[0.001] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.ingest.embed.encode_texts", fake_encode)
    run_ingest_job(db_session, job_id, work_id)
    db_session.flush()

    passages = list(db_session.scalars(select(Passage).where(Passage.work_id == work_id)).all())
    assert len(passages) >= 1
    joined = " ".join(p.cleaned_text for p in passages)
    assert "worker pdf unique phrase plugh" in joined

    work = db_session.get(Work, work_id)
    assert work is not None
    assert work.title == "Worker PDF Title"
    assert work.author == "Worker PDF Author"
