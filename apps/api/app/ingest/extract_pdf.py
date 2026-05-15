from __future__ import annotations

import fitz

from app.ingest.metadata import WorkMetadata


def extract_pdf_text(file_path: str) -> str:
    doc = fitz.open(file_path)
    try:
        parts: list[str] = []
        for page in doc:
            t = page.get_text()
            if t and t.strip():
                parts.append(t.strip())
        return "\n\n".join(parts)
    finally:
        doc.close()


def extract_pdf_metadata(file_path: str) -> WorkMetadata:
    doc = fitz.open(file_path)
    try:
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip() or None
        author = (meta.get("author") or "").strip() or None
        return WorkMetadata(title=title, author=author, language=None)
    finally:
        doc.close()
