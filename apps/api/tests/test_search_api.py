from __future__ import annotations

import uuid

from app.api.search import get_encode_query_vector
from app.db.models import IngestionState, Passage, PassageEmbedding, Source, SourceType, Work
from app.ingest.embed import EMBEDDING_DIM, EMBEDDING_MODEL
from app.main import app


def _u(i: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[i] = 1.0
    return v


def _seed_work_with_passage(
    db_session,
    *,
    source_type: SourceType = SourceType.gutenberg,
    author: str = "Plato",
    title: str = "Republic",
    language: str | None = "en",
    cleaned_text: str = "Short.",
    vec: list[float] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    vec = vec or _u(0)
    source = Source(
        id=uuid.uuid4(),
        source_type=source_type,
        locator=str(uuid.uuid4()),
        canonical_url="https://example.com",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        title=title,
        author=author,
        language=language,
        ingestion_state=IngestionState.complete,
    )
    passage = Passage(
        id=uuid.uuid4(),
        work_id=work.id,
        passage_index=1,
        cleaned_text=cleaned_text,
        citation_string="c1",
        chunker_version="mvp-1",
    )
    emb = PassageEmbedding(
        id=uuid.uuid4(),
        passage_id=passage.id,
        work_id=work.id,
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=EMBEDDING_DIM,
        embedding=vec,
    )
    db_session.add_all([source, work, passage, emb])
    return work.id, passage.id


def _override_encode(fn):
    app.dependency_overrides[get_encode_query_vector] = lambda: fn


def _clear_encode_override():
    app.dependency_overrides.pop(get_encode_query_vector, None)


def test_search_k_default_and_max(client, db_session):
    for _ in range(12):
        _seed_work_with_passage(db_session, cleaned_text="hello")

    _override_encode(lambda _q: _u(0))
    try:
        resp = client.post("/api/search", json={"query": "why virtue"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["k"] == 10
        assert len(body["results"]) == 10

        bad = client.post("/api/search", json={"query": "why virtue", "k": 51})
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_k"

        bad2 = client.post("/api/search", json={"query": "why virtue", "k": 0})
        assert bad2.status_code == 400
    finally:
        _clear_encode_override()


def test_search_empty_query(client, db_session):
    r = client.post("/api/search", json={"query": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_query"


def test_search_invalid_source_type_filter(client, db_session):
    _seed_work_with_passage(db_session)
    _override_encode(lambda _q: _u(0))
    try:
        r = client.post(
            "/api/search",
            json={"query": "x", "filters": {"source_type": ["not-a-type"]}},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_filter"
    finally:
        _clear_encode_override()


def test_search_orders_by_rrf_score(client, db_session):
    w_close, p_close = _seed_work_with_passage(db_session, cleaned_text="alpha bravo", vec=_u(0))
    _seed_work_with_passage(db_session, cleaned_text="charlie delta", vec=_u(1))

    _override_encode(lambda _q: _u(0))
    try:
        resp = client.post("/api/search", json={"query": "anything", "k": 10})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert results[0]["passage_id"] == str(p_close)
        assert results[0]["work_id"] == str(w_close)
        assert results[0]["rrf_score"] >= results[1]["rrf_score"]
    finally:
        _clear_encode_override()


def test_search_snippet_word_boundary(client, db_session):
    long_text = "word1 " * 80
    _seed_work_with_passage(db_session, cleaned_text=long_text)

    _override_encode(lambda _q: _u(0))
    try:
        resp = client.post("/api/search", json={"query": "word1", "k": 5})
        assert resp.status_code == 200
        snippet = resp.json()["results"][0]["cleaned_text_snippet"]
        assert len(snippet) <= 300
        assert snippet.endswith("word1")
    finally:
        _clear_encode_override()


def test_search_filter_source_type(client, db_session):
    wg, _ = _seed_work_with_passage(db_session, source_type=SourceType.gutenberg)
    ww, pw = _seed_work_with_passage(db_session, source_type=SourceType.wikisource)

    _override_encode(lambda _q: _u(0))
    try:
        r_all = client.post("/api/search", json={"query": "q", "k": 10})
        assert len(r_all.json()["results"]) == 2

        r_gut = client.post(
            "/api/search",
            json={"query": "q", "k": 10, "filters": {"source_type": ["gutenberg"]}},
        )
        ids = {x["work_id"] for x in r_gut.json()["results"]}
        assert ids == {str(wg)}

        r_ws = client.post(
            "/api/search",
            json={"query": "q", "k": 10, "filters": {"source_type": ["gutenberg", "wikisource"]}},
        )
        assert len(r_ws.json()["results"]) == 2
    finally:
        _clear_encode_override()


def test_search_filter_author_or(client, db_session):
    _seed_work_with_passage(db_session, author="Alice Author")
    wb, pb = _seed_work_with_passage(db_session, author="Bob Builder")

    _override_encode(lambda _q: _u(0))
    try:
        r = client.post(
            "/api/search",
            json={
                "query": "q",
                "k": 10,
                "filters": {"author": ["ZZZ", "Bob"]},
            },
        )
        res = r.json()["results"]
        assert len(res) == 1
        assert res[0]["work_id"] == str(wb)
        assert res[0]["passage_id"] == str(pb)
    finally:
        _clear_encode_override()


def test_search_filter_work_ids_and_language(client, db_session):
    wa, pa = _seed_work_with_passage(db_session, language="en")
    wb, _ = _seed_work_with_passage(db_session, language="de")

    _override_encode(lambda _q: _u(0))
    try:
        r = client.post(
            "/api/search",
            json={
                "query": "q",
                "k": 10,
                "filters": {"work_ids": [str(wa)], "language": ["de"]},
            },
        )
        assert r.json()["results"] == []

        r2 = client.post(
            "/api/search",
            json={"query": "q", "k": 10, "filters": {"work_ids": [str(wa)], "language": ["en"]}},
        )
        assert len(r2.json()["results"]) == 1
        assert r2.json()["results"][0]["passage_id"] == str(pa)
    finally:
        _clear_encode_override()


def test_search_meta_embedding_model(client, db_session):
    _seed_work_with_passage(db_session)
    _override_encode(lambda _q: _u(0))
    try:
        r = client.post("/api/search", json={"query": "hello"})
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["embedding_model"] == EMBEDDING_MODEL
        assert meta["retrieval"] == "hybrid"
    finally:
        _clear_encode_override()


def test_search_hybrid_surfaces_fts_match(client, db_session):
    """
    A passage with a keyword match but no vector similarity should still surface
    via the FTS arm. Seed two passages: one semantically close to the query vector
    (vec unit-0), one containing the keyword "Wickham" but semantically orthogonal
    (vec unit-1). The query is unit-0 vector + "Wickham" text. Both should appear.
    """
    # Passage A: semantically close to query vector, no keyword
    _seed_work_with_passage(
        db_session,
        cleaned_text="Elizabeth smiled at the gathering.",
        vec=_u(0),
    )
    # Passage B: contains the keyword "Wickham", semantically orthogonal
    _seed_work_with_passage(
        db_session,
        cleaned_text="Wickham approached with his usual charm.",
        vec=_u(1),
    )

    _override_encode(lambda _q: _u(0))  # vector arm favours passage A
    try:
        resp = client.post("/api/search", json={"query": "Wickham", "k": 10})
        assert resp.status_code == 200
        results = resp.json()["results"]
        texts = [r["cleaned_text_snippet"] for r in results]
        assert any("Wickham" in t for t in texts), "FTS arm should surface the Wickham passage"
        assert any("Elizabeth" in t for t in texts), "Vector arm should surface the Elizabeth passage"
    finally:
        _clear_encode_override()
