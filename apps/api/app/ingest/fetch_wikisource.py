from __future__ import annotations

import hashlib
from urllib.parse import quote, unquote, urlparse

import httpx

from app.ingest.canonicalize import canonicalize_wikisource
from app.ingest.fetch_gutenberg import ArtifactFetchResult


def _rest_html_url(canonical_locator: str) -> str:
    canon = canonicalize_wikisource(canonical_locator)
    parsed = urlparse(canon.locator)
    title = unquote(parsed.path.removeprefix("/wiki/"))
    encoded = quote(title, safe="/:")
    return f"https://en.wikisource.org/api/rest_v1/page/html/{encoded}"


def fetch_wikisource(
    canonical_locator: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 60.0,
) -> ArtifactFetchResult:
    """
    Fetch rendered HTML via MediaWiki REST `page/html/{Title}` (spec).

    `canonical_locator` should be the canonical `https://en.wikisource.org/wiki/...` URL.
    """
    close_client = False
    if client is None:
        client = httpx.Client(timeout=timeout)
        close_client = True
    try:
        url = _rest_html_url(canonical_locator)
        resp = client.get(url, follow_redirects=True)
        body = resp.content
        digest = hashlib.sha256(body).hexdigest() if body else hashlib.sha256(b"").hexdigest()
        if resp.status_code == 200:
            return ArtifactFetchResult(
                raw_text=None,
                raw_html=resp.text,
                retrieval_url=url,
                final_url=str(resp.url),
                http_status=resp.status_code,
                content_type=resp.headers.get("content-type"),
                content_sha256=digest,
            )
        return ArtifactFetchResult(
            raw_text=None,
            raw_html=None,
            retrieval_url=url,
            final_url=str(resp.url),
            http_status=resp.status_code,
            content_type=resp.headers.get("content-type"),
            content_sha256=digest,
        )
    finally:
        if close_client:
            client.close()
