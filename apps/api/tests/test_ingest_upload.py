from __future__ import annotations

import os
import uuid
from pathlib import Path

import fitz
from ebooklib import epub

from app.db.models import IngestionJob, IngestionState, JobStatus, Work
from app.settings import settings


def _write_minimal_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("up-test")
    book.set_title("Upload EPUB Title")
    book.set_language("en")
    book.add_author("Upload Author")
    ch = epub.EpubHtml(title="C", file_name="c.xhtml", lang="en")
    ch.set_content(
        '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
        "<body><p>upload ingest unique phrase.</p></body></html>"
    )
    book.add_item(ch)
    book.toc = [ch]
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [nav, ch]
    epub.write_epub(str(path), book)


def _write_minimal_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "pdf upload unique phrase.")
        doc.save(str(path))
    finally:
        doc.close()


def test_upload_epub_creates_job_and_file(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    epub_path = tmp_path / "book.epub"
    _write_minimal_epub(epub_path)
    body = epub_path.read_bytes()

    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("book.epub", body, "application/epub+zip")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["work_id"]
    assert data["job_id"]

    work_id = uuid.UUID(data["work_id"])
    work = db_session.get(Work, work_id)
    assert work is not None
    assert work.source_id
    upload_dir = os.path.join(tmp_path, str(work.source_id))
    assert os.path.isdir(upload_dir)
    assert any(f.endswith(".epub") for f in os.listdir(upload_dir))


def test_upload_pdf_creates_job(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    pdf_path = tmp_path / "doc.pdf"
    _write_minimal_pdf(pdf_path)
    body = pdf_path.read_bytes()

    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("doc.pdf", body, "application/pdf")},
    )
    assert resp.status_code == 202
    assert resp.json()["job_id"]


def test_upload_duplicate_when_complete_returns_no_job(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    epub_path = tmp_path / "dup.epub"
    _write_minimal_epub(epub_path)
    body = epub_path.read_bytes()

    first = client.post("/api/ingest/upload", files={"file": ("dup.epub", body, "application/epub+zip")})
    assert first.status_code == 202
    work_id = uuid.UUID(first.json()["work_id"])
    work = db_session.get(Work, work_id)
    work.ingestion_state = IngestionState.complete
    job_id = uuid.UUID(first.json()["job_id"])
    job = db_session.get(IngestionJob, job_id)
    assert job is not None
    job.status = JobStatus.succeeded
    db_session.flush()

    second = client.post("/api/ingest/upload", files={"file": ("dup.epub", body, "application/epub+zip")})
    assert second.status_code == 200
    assert second.json()["job_id"] is None


def test_upload_invalid_extension(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_file"


def test_upload_too_large(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr("app.api.ingest.MAX_UPLOAD_BYTES", 5)
    resp = client.post(
        "/api/ingest/upload",
        files={"file": ("big.epub", b"123456789", "application/epub+zip")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_file"


def test_ingest_json_rejects_epub(client):
    resp = client.post("/api/ingest", json={"source_type": "epub", "locator": "deadbeef"})
    assert resp.status_code == 400
