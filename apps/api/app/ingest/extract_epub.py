from __future__ import annotations

import ebooklib
from ebooklib import epub
from ebooklib.epub import EpubNav

from app.ingest.metadata import WorkMetadata
from app.ingest.normalize import normalize_wikisource_html


def _first_dc_value(book: epub.EpubBook, name: str) -> str | None:
    data = book.get_metadata("DC", name)
    if not data:
        return None
    val = data[0][0]
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def extract_epub_metadata(file_path: str) -> WorkMetadata:
    book = epub.read_epub(file_path)
    return WorkMetadata(
        title=_first_dc_value(book, "title"),
        author=_first_dc_value(book, "creator"),
        language=_first_dc_value(book, "language"),
    )


def extract_epub_text(file_path: str) -> str:
    book = epub.read_epub(file_path)
    parts: list[str] = []
    for idref, _linear in book.spine:
        if not idref:
            continue
        try:
            item = book.get_item_with_id(idref)
        except (KeyError, IndexError):
            continue
        if item is None or isinstance(item, EpubNav):
            continue
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        raw = item.get_content()
        if not raw:
            continue
        html_str = raw.decode("utf-8", errors="replace")
        txt = normalize_wikisource_html(html_str)
        if txt:
            parts.append(txt)
    return "\n\n".join(parts)
