from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ArtifactFetchResult:
    """Fields aligned with `source_artifacts` for successful 2xx fetches."""

    raw_text: str | None
    raw_html: str | None
    retrieval_url: str
    final_url: str
    http_status: int
    content_type: str | None
    content_sha256: str

    def ok_for_source_artifact_row(self) -> bool:
        """DB check: exactly one of raw_text / raw_html is set (2xx bodies only)."""
        if self.http_status < 200 or self.http_status > 299:
            return False
        return (self.raw_text is None) != (self.raw_html is None)


def fetch_gutenberg(
    locator_id: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 60.0,
) -> ArtifactFetchResult:
    """
    Fetch UTF-8 plain text: try `{id}-0.txt` then `{id}.txt` (spec).

    On non-2xx responses, `raw_text` and `raw_html` may both be ``None``;
    callers must not insert failing rows without handling the XOR constraint.
    """
    close_client = False
    if client is None:
        client = httpx.Client(timeout=timeout)
        close_client = True
    try:
        base = f"https://www.gutenberg.org/files/{locator_id}/{locator_id}"
        candidates = (f"{base}-0.txt", f"{base}.txt")
        last: httpx.Response | None = None
        for url in candidates:
            resp = client.get(url, follow_redirects=True)
            last = resp
            if resp.status_code == 200:
                body = resp.content
                digest = hashlib.sha256(body).hexdigest()
                text = body.decode("utf-8")
                return ArtifactFetchResult(
                    raw_text=text,
                    raw_html=None,
                    retrieval_url=url,
                    final_url=str(resp.url),
                    http_status=resp.status_code,
                    content_type=resp.headers.get("content-type"),
                    content_sha256=digest,
                )
            if resp.status_code != 404:
                body = resp.content
                digest = hashlib.sha256(body).hexdigest() if body else hashlib.sha256(b"").hexdigest()
                return ArtifactFetchResult(
                    raw_text=None,
                    raw_html=None,
                    retrieval_url=url,
                    final_url=str(resp.url),
                    http_status=resp.status_code,
                    content_type=resp.headers.get("content-type"),
                    content_sha256=digest,
                )
        assert last is not None
        body = last.content
        digest = hashlib.sha256(body).hexdigest() if body else hashlib.sha256(b"").hexdigest()
        return ArtifactFetchResult(
            raw_text=None,
            raw_html=None,
            retrieval_url=candidates[-1],
            final_url=str(last.url),
            http_status=last.status_code,
            content_type=last.headers.get("content-type"),
            content_sha256=digest,
        )
    finally:
        if close_client:
            client.close()
