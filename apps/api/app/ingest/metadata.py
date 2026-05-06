from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class WorkMetadata:
    title: str | None = None
    author: str | None = None
    language: str | None = None


_FIELD_RE = re.compile(r"^(Title|Author|Language):\s*(.+?)\s*$", re.IGNORECASE)


def extract_gutenberg_metadata(raw_text: str) -> WorkMetadata:
    """
    Best-effort extraction from Gutenberg plain text header (pre-boilerplate strip).

    Typical header contains lines like:
      Title: Pride and Prejudice
      Author: Jane Austen
      Language: English
    """
    title: str | None = None
    author: str | None = None
    language: str | None = None

    # Only scan the early portion of the file.
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
            # Normalize common values a bit.
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

