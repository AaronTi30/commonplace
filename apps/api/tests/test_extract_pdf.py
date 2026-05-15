from __future__ import annotations

from pathlib import Path

import fitz

from app.ingest.extract_pdf import extract_pdf_metadata, extract_pdf_text


def _write_minimal_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "Unique phrase pdf fixture.")
        doc.set_metadata({"title": "PDF Fixture Title", "author": "PDF Fixture Author"})
        doc.save(str(path))
    finally:
        doc.close()


def test_extract_pdf_text_non_empty(tmp_path: Path) -> None:
    p = tmp_path / "t.pdf"
    _write_minimal_pdf(p)
    text = extract_pdf_text(str(p))
    assert "Unique phrase pdf fixture" in text


def test_extract_pdf_metadata(tmp_path: Path) -> None:
    p = tmp_path / "t.pdf"
    _write_minimal_pdf(p)
    md = extract_pdf_metadata(str(p))
    assert md.title == "PDF Fixture Title"
    assert md.author == "PDF Fixture Author"
    assert md.language is None
