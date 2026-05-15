from __future__ import annotations

import json
import uuid

from app.api.search import get_encode_query_vector
from app.db.models import IngestionState, Passage, PassageEmbedding, Source, SourceType, Work
from app.ingest.embed import EMBEDDING_DIM, EMBEDDING_MODEL
from app.llm.ollama_client import get_ollama_client
from app.main import app


def _u(i: int) -> list[float]:
    v = [0.0] * EMBEDDING_DIM
    v[i] = 1.0
    return v


def _seed_work_with_passage(
    db_session,
    *,
    cleaned_text: str = "Short.",
    vec: list[float] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    vec = vec or _u(0)
    source = Source(
        id=uuid.uuid4(),
        source_type=SourceType.gutenberg,
        locator=str(uuid.uuid4()),
        canonical_url="https://example.com",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        title="Test",
        author="Author",
        language="en",
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


class FakeStreamingOllama:
    """Fake OllamaClient that yields a fixed list of tokens from stream_generate."""

    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    def generate(self, prompt: str) -> str:
        return "".join(self._tokens)

    async def stream_generate(self, prompt: str):
        for token in self._tokens:
            yield token


def _parse_sse_events(lines) -> list[dict]:
    events = []
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def test_ollama_client_has_stream_generate():
    from app.llm.ollama_client import OllamaClient
    import inspect

    assert hasattr(OllamaClient, "stream_generate"), "OllamaClient must have stream_generate"
    assert inspect.isasyncgenfunction(OllamaClient.stream_generate), "stream_generate must be an async generator"


def test_ask_stream_emits_passages_then_tokens_then_done(client, db_session):
    _, p1 = _seed_work_with_passage(db_session, cleaned_text="Virtue is knowledge.", vec=_u(0))
    tokens = ["Virtue ", "is [1]", " the key."]
    fake = FakeStreamingOllama(tokens)
    app.dependency_overrides[get_ollama_client] = lambda: fake
    _override_encode(lambda _q: _u(0))
    try:
        with client.stream("POST", "/api/ask/stream", json={"query": "What is virtue?", "k": 5}) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            lines = list(r.iter_lines())

        events = _parse_sse_events(lines)
        types = [e["type"] for e in events]

        assert types[0] == "passages", f"First event must be 'passages', got {types}"
        assert types[-1] == "done", f"Last event must be 'done', got {types}"
        assert all(t == "token" for t in types[1:-1]), f"Middle events must all be 'token', got {types[1:-1]}"

        passages_event = events[0]
        assert len(passages_event["retrieved_passages"]) == 1
        assert passages_event["retrieved_passages"][0]["passage_id"] == str(p1)
        assert "k" in passages_event["meta"]

        token_texts = [e["text"] for e in events if e["type"] == "token"]
        assert "".join(token_texts) == "Virtue is [1] the key."

        done_event = events[-1]
        assert done_event["cited_passage_ids"] == [str(p1)]
    finally:
        _clear_encode_override()
        app.dependency_overrides.pop(get_ollama_client, None)


def test_ask_stream_error_event_on_ollama_failure(client, db_session):
    _seed_work_with_passage(db_session)

    class ErrorStreamingOllama:
        def generate(self, prompt: str) -> str:
            return ""

        async def stream_generate(self, prompt: str):
            raise RuntimeError("Ollama is down")
            yield

    app.dependency_overrides[get_ollama_client] = lambda: ErrorStreamingOllama()
    _override_encode(lambda _q: _u(0))
    try:
        with client.stream("POST", "/api/ask/stream", json={"query": "q", "k": 5}) as r:
            assert r.status_code == 200
            lines = list(r.iter_lines())

        events = _parse_sse_events(lines)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "Ollama is down" in error_events[0]["message"]
    finally:
        _clear_encode_override()
        app.dependency_overrides.pop(get_ollama_client, None)


def test_ask_stream_validation_rejects_empty_query(client, db_session):
    r = client.post("/api/ask/stream", json={"query": "  ", "k": 5})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_query"


def test_ask_stream_validation_rejects_bad_k(client, db_session):
    r = client.post("/api/ask/stream", json={"query": "hi", "k": 99})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_k"
