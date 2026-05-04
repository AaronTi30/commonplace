from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote, urlparse, urlunparse


@dataclass(frozen=True)
class CanonicalGutenberg:
    source_type: Literal["gutenberg"]
    locator: str
    canonical_url: str


@dataclass(frozen=True)
class CanonicalWikisource:
    source_type: Literal["wikisource"]
    locator: str
    canonical_url: str


def _extract_gutenberg_id_from_url(url: str) -> str | None:
    for pattern in (
        r"/ebooks/(\d+)",
        r"/files/(\d+)/",
        r"/cache/epub/(\d+)/",
    ):
        m = re.search(pattern, url, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def canonicalize_gutenberg(locator_or_url: str) -> CanonicalGutenberg:
    """
    Extract the decimal Gutenberg ID and build the display canonical URL.

    Accepts a bare numeric string or common Project Gutenberg URLs.
    """
    raw = locator_or_url.strip()
    if not raw:
        raise ValueError("Gutenberg locator is empty")

    if raw.isdigit():
        gid = raw.lstrip("0") or "0"
    else:
        extracted = _extract_gutenberg_id_from_url(raw)
        if not extracted:
            raise ValueError(f"Could not extract a Gutenberg ID from: {locator_or_url!r}")
        gid = extracted.lstrip("0") or "0"

    if not gid.isdigit():
        raise ValueError(f"Invalid Gutenberg ID: {gid!r}")

    canonical_url = f"https://www.gutenberg.org/ebooks/{gid}"
    return CanonicalGutenberg(source_type="gutenberg", locator=gid, canonical_url=canonical_url)


def canonicalize_wikisource(url: str) -> CanonicalWikisource:
    """
    Canonical Wikisource locator for MVP: https://en.wikisource.org/wiki/<Title>.

    Rules (spec): https scheme, drop query + fragment, host en.wikisource.org,
    path /wiki/<Title> with spaces as underscores.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("Wikisource URL is empty")

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host.endswith("wikisource.org"):
        raise ValueError("URL must be a *.wikisource.org host")

    path = unquote(parsed.path or "")
    if not path.startswith("/wiki/"):
        raise ValueError("Wikisource URL must include a /wiki/<Title> path")

    title = path[len("/wiki/") :].strip("/")
    if not title:
        raise ValueError("Wikisource /wiki/ path is missing a title")

    title = title.replace(" ", "_")
    canonical_path = "/wiki/" + title
    locator = urlunparse(("https", "en.wikisource.org", canonical_path, "", "", ""))
    return CanonicalWikisource(source_type="wikisource", locator=locator, canonical_url=locator)
