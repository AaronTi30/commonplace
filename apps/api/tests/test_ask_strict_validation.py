from __future__ import annotations

import json
import uuid

from app.api.search import get_encode_query_vector
from app.db.models import IngestionState, Passage, PassageEmbedding, Source, SourceType, Work
from app.ingest.embed import EMBEDDING_DIM, EMBEDDING_MODEL
from app.llm.grounding import (
    extract_json_object,
    normalize_for_quote_validation,
    parse_strict_answer,
)
from app.llm.ollama_client import get_ollama_client
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


class FakeOllama:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._i = 0

    def generate(self, prompt: str) -> str:
        if self._i >= len(self._responses):
            return ""
        r = self._responses[self._i]
        self._i += 1
        return r


def _override_ollama(fake: FakeOllama) -> None:
    app.dependency_overrides[get_ollama_client] = lambda: fake


def _clear_ollama_override() -> None:
    app.dependency_overrides.pop(get_ollama_client, None)


def _strict_json_ok(passage_id: uuid.UUID, quote: str, claim: str = "Test claim.") -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "claim": claim,
                    "supports": [{"passage_id": str(passage_id), "quote": quote}],
                }
            ]
        }
    )


def test_normalize_for_quote_validation_curly_quotes():
    passage = "He said \u201chello\u201d to the world."
    quote = '"hello"'
    assert normalize_for_quote_validation(quote) in normalize_for_quote_validation(passage)


def test_extract_json_from_markdown_fence():
    raw = """Here is JSON:
```json
{"claims": []}
```
"""
    assert extract_json_object(raw) == {"claims": []}


def test_parse_strict_answer_schema():
    text = '{"claims":[{"claim":"x","supports":[{"passage_id":"550e8400-e29b-41d4-a716-446655440000","quote":"y"}]}]}'
    p = parse_strict_answer(text)
    assert p is not None
    assert p.claims[0].supports[0].quote == "y"


def test_strict_mode_passes_validation_first_try(client, db_session):
    _, pid = _seed_work_with_passage(db_session, cleaned_text="Virtue is the highest good.")
    payload = _strict_json_ok(pid, "Virtue is the highest good.")

    _override_encode(lambda _q: _u(0))
    _override_ollama(FakeOllama([payload]))
    try:
        r = client.post(
            "/api/ask",
            json={"query": "What about virtue?", "k": 5, "mode": "strict"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["strict_validation"] == {"passed": True, "attempts": 1}
        assert body["cited_passage_ids"] == [str(pid)]
        assert "Virtue is the highest good" in body["answer_markdown"]
    finally:
        _clear_encode_override()
        _clear_ollama_override()


def test_strict_mode_repairs_once_then_succeeds(client, db_session):
    _, pid = _seed_work_with_passage(db_session, cleaned_text="Justice is the bond of men in states.")
    bad = _strict_json_ok(pid, "this substring does not exist in passage")
    good = _strict_json_ok(pid, "Justice is the bond of men in states.")

    _override_encode(lambda _q: _u(0))
    _override_ollama(FakeOllama([bad, good]))
    try:
        r = client.post("/api/ask", json={"query": "Justice?", "k": 5, "mode": "strict"})
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["strict_validation"] == {"passed": True, "attempts": 2}
        assert "Justice is the bond of men in states" in body["answer_markdown"]
    finally:
        _clear_encode_override()
        _clear_ollama_override()


def test_strict_mode_insufficient_evidence_after_two_failures(client, db_session):
    _, pid = _seed_work_with_passage(db_session, cleaned_text="Unique passage text.")
    bad = _strict_json_ok(pid, "wrong quote always")

    _override_encode(lambda _q: _u(0))
    _override_ollama(FakeOllama([bad, bad]))
    try:
        r = client.post("/api/ask", json={"query": "q", "k": 5, "mode": "strict"})
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["strict_validation"] == {"passed": False, "attempts": 2}
        assert body["cited_passage_ids"] == []
        assert "Insufficient evidence" in body["answer_markdown"]
    finally:
        _clear_encode_override()
        _clear_ollama_override()


def test_fluent_mode_extracts_bracket_citations(client, db_session):
    _, p1 = _seed_work_with_passage(db_session, cleaned_text="First passage.", vec=_u(0))
    _, p2 = _seed_work_with_passage(db_session, cleaned_text="Second passage.", vec=_u(1))

    _override_encode(lambda _q: _u(0))
    _override_ollama(FakeOllama(["Answer using [1] then [2]."]))
    try:
        r = client.post("/api/ask", json={"query": "Explain.", "k": 5, "mode": "fluent"})
        assert r.status_code == 200
        body = r.json()
        assert "strict_validation" not in body["meta"]
        assert body["cited_passage_ids"] == [str(p1), str(p2)]
    finally:
        _clear_encode_override()
        _clear_ollama_override()


def test_fluent_mode_retries_once_if_missing_citations(client, db_session):
    _, p1 = _seed_work_with_passage(db_session, cleaned_text="First passage.", vec=_u(0))
    _, p2 = _seed_work_with_passage(db_session, cleaned_text="Second passage.", vec=_u(1))

    _override_encode(lambda _q: _u(0))
    _override_ollama(
        FakeOllama(
            [
                "Here is an answer but I forgot citations.",
                "Retry with cites [1] and [2].",
            ]
        )
    )
    try:
        r = client.post("/api/ask", json={"query": "Explain.", "k": 5, "mode": "fluent"})
        assert r.status_code == 200
        body = r.json()
        assert body["cited_passage_ids"] == [str(p1), str(p2)]
    finally:
        _clear_encode_override()
        _clear_ollama_override()


def test_ask_k_bounds(client, db_session):
    _seed_work_with_passage(db_session)
    r = client.post("/api/ask", json={"query": "hi", "k": 21, "mode": "strict"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_k"


def test_ask_invalid_filter(client, db_session):
    _seed_work_with_passage(db_session)
    _override_encode(lambda _q: _u(0))
    try:
        r = client.post(
            "/api/ask",
            json={
                "query": "q",
                "k": 3,
                "mode": "strict",
                "filters": {"source_type": ["nope"]},
            },
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_filter"
    finally:
        _clear_encode_override()
