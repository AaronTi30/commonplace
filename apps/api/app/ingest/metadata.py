from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx


@dataclass(frozen=True)
class WorkMetadata:
    title: str | None = None
    author: str | None = None
    language: str | None = None


_FIELD_RE = re.compile(r"^(Title|Author|Language):\s*(.+?)\s*$", re.IGNORECASE)


def fetch_gutenberg_metadata_api(locator_id: str, *, timeout: float = 10.0) -> WorkMetadata:
    """
    Fetch structured metadata from the Gutendex API (gutendex.com).
    Returns a WorkMetadata with whatever fields are available; falls back to
    all-None if the request fails or the book isn't found.
    """
    try:
        resp = httpx.get(
            f"https://gutendex.com/books/{locator_id}",
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return WorkMetadata()
        data = resp.json()
        title = data.get("title") or None
        authors = data.get("authors") or []
        author: str | None = None
        if authors:
            a = authors[0]
            name = a.get("name") or ""
            # Gutendex returns "Austen, Jane" — flip to "Jane Austen"
            if "," in name:
                last, first = name.split(",", 1)
                name = f"{first.strip()} {last.strip()}"
            author = name or None
        languages = data.get("languages") or []
        language = languages[0] if languages else None
        return WorkMetadata(title=title, author=author, language=language)
    except Exception:
        return WorkMetadata()


def extract_gutenberg_metadata(raw_text: str) -> WorkMetadata:
    """
    Best-effort extraction from Gutenberg plain text header.
    Scans for 'Title:', 'Author:', 'Language:' lines in the first 250 lines.
    Returns all-None if not found (old-format files have no such header).
    """
    title: str | None = None
    author: str | None = None
    language: str | None = None

    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")[:250]
    for line in lines:
        m = _FIELD_RE.match(line.strip())
        if not m:
            continue
        field = m.group(1).lower()
        value = m.group(2).strip()
        if field == "title" and not title:
            title = value
        elif field == "author" and not author:
            author = value
        elif field == "language" and not language:
            language = value
        if title and author and language:
            break

    return WorkMetadata(title=title, author=author, language=language)


_TITLE_TAG_RE = re.compile(r"(?is)<\s*title[^>]*>(.*?)</\s*title\s*>")
_H1_RE = re.compile(r"(?is)<\s*h1[^>]*>(.*?)</\s*h1\s*>")
_TAG_RE = re.compile(r"(?is)<[^>]+>")


def extract_wikisource_metadata(*, canonical_locator: str, raw_html: str) -> WorkMetadata:
    """
    MVP: derive title from HTML <title>/<h1> or URL path, author unknown.
    """
    title: str | None = None

    m = _TITLE_TAG_RE.search(raw_html)
    if m:
        t = _TAG_RE.sub("", m.group(1)).strip()
        # MediaWiki titles often include " - Wikisource"
        if " - " in t:
            t = t.split(" - ", 1)[0].strip()
        title = t or None

    if not title:
        m2 = _H1_RE.search(raw_html)
        if m2:
            title = _TAG_RE.sub("", m2.group(1)).strip() or None

    if not title:
        parsed = urlparse(canonical_locator)
        path = parsed.path.removeprefix("/wiki/")
        if path:
            title = unquote(path).replace("_", " ").strip() or None

    return WorkMetadata(title=title, author=None, language="en")

