from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from ebooklib import epub
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


def _write_minimal_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("wk-test")
    book.set_title("Worker EPUB Title")
    book.set_language("fr")
    book.add_author("Worker Author")
    ch = epub.EpubHtml(title="C", file_name="w.xhtml", lang="fr")
    ch.set_content(
        '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
        "<body><p>worker epub unique phrase xyzzy.</p></body></html>"
    )
    book.add_item(ch)
    book.toc = [ch]
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [nav, ch]
    epub.write_epub(str(path), book)


def test_run_ingest_job_epub_from_artifact_file(monkeypatch, db_session, tmp_path):
    epub_path = tmp_path / "seed.epub"
    _write_minimal_epub(epub_path)
    data = epub_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()

    upload_root = tmp_path / "uploads"
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    job_id = uuid.uuid4()

    dest_dir = upload_root / str(source_id)
    dest_dir.mkdir(parents=True)
    stored = dest_dir / "seed.epub"
    shutil.copy(epub_path, stored)

    db_session.add(
        Source(
            id=source_id,
            source_type=SourceType.epub,
            locator=digest,
            canonical_url="file://seed.epub",
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
            retrieval_url="file://seed.epub",
            final_url="file://seed.epub",
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
    assert "worker epub unique phrase xyzzy" in joined

    work = db_session.get(Work, work_id)
    assert work is not None
    assert work.title == "Worker EPUB Title"
    assert work.author == "Worker Author"
    assert work.language == "fr"
