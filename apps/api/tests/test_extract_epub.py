from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from app.ingest.extract_epub import extract_epub_metadata, extract_epub_text


def _write_minimal_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Fixture Title")
    book.set_language("en")
    book.add_author("Fixture Author")
    ch = epub.EpubHtml(title="Ch1", file_name="c1.xhtml", lang="en")
    ch.set_content(
        '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
        "<body><p>Unique phrase epub fixture.</p></body></html>"
    )
    book.add_item(ch)
    book.toc = [ch]
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = [nav, ch]
    epub.write_epub(str(path), book)


def test_extract_epub_text_non_empty(tmp_path: Path) -> None:
    p = tmp_path / "t.epub"
    _write_minimal_epub(p)
    text = extract_epub_text(str(p))
    assert "Unique phrase epub fixture" in text


def test_extract_epub_metadata(tmp_path: Path) -> None:
    p = tmp_path / "t.epub"
    _write_minimal_epub(p)
    md = extract_epub_metadata(str(p))
    assert md.title == "Fixture Title"
    assert md.author == "Fixture Author"
    assert md.language == "en"
