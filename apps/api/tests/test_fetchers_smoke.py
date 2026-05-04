from __future__ import annotations

import hashlib

import httpx

from app.ingest.fetch_gutenberg import fetch_gutenberg
from app.ingest.fetch_wikisource import fetch_wikisource


def test_fetch_gutenberg_prefers_dash_zero_then_plain_txt():
    body = b"The Project Gutenberg eBook\n\nHello"
    digest = hashlib.sha256(body).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("1342-0.txt"):
            return httpx.Response(404)
        if u.endswith("1342.txt"):
            return httpx.Response(200, content=body, headers={"content-type": "text/plain; charset=utf-8"})
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        r = fetch_gutenberg("1342", client=client)

    assert r.http_status == 200
    assert r.raw_html is None
    assert r.raw_text == body.decode("utf-8")
    assert r.content_sha256 == digest
    assert r.retrieval_url.endswith("1342.txt")
    assert r.ok_for_source_artifact_row()


def test_fetch_gutenberg_uses_dash_zero_when_present():
    body = b"alpha"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("9-0.txt"):
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        r = fetch_gutenberg("9", client=client)

    assert r.http_status == 200
    assert r.raw_text == "alpha"
    assert r.retrieval_url.endswith("9-0.txt")
    assert r.ok_for_source_artifact_row()


def test_fetch_wikisource_returns_html_xor():
    html = "<html><body>ok</body></html>"
    body = html.encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/api/rest_v1/page/html/" in str(request.url)
        assert str(request.url).endswith("Republic")
        return httpx.Response(200, content=body, headers={"content-type": "text/html; charset=utf-8"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        r = fetch_wikisource("https://en.wikisource.org/wiki/Republic", client=client)

    assert r.http_status == 200
    assert r.raw_text is None
    assert r.raw_html == html
    assert r.content_sha256 == digest
    assert r.ok_for_source_artifact_row()


def test_fetch_wikisource_encodes_subpage_title():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=b"<html/>")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        fetch_wikisource("https://en.wikisource.org/wiki/Bhagavad_Gita/Chapter_1", client=client)

    assert requested
    assert "Bhagavad_Gita%2FChapter_1" in requested[0] or "Bhagavad_Gita/Chapter_1" in requested[0]


def test_fetch_wikisource_non_200_not_artifact_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"busy")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        r = fetch_wikisource("https://en.wikisource.org/wiki/Republic", client=client)

    assert r.http_status == 503
    assert r.raw_text is None
    assert r.raw_html is None
    assert not r.ok_for_source_artifact_row()
