from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db.models import IngestionState, Passage, PassageEmbedding, Source, SourceType, Work
from app.ingest.embed import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    embed_passages_for_work,
    insert_passage_embeddings_idempotent,
)


def _seed_work_with_passage(db_session):
    source = Source(
        id=uuid.uuid4(),
        source_type=SourceType.gutenberg,
        locator="1",
        canonical_url="https://www.gutenberg.org/ebooks/1",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        title="T",
        author="A",
        ingestion_state=IngestionState.running,
    )
    passage = Passage(
        id=uuid.uuid4(),
        work_id=work.id,
        passage_index=1,
        raw_text="hello",
        cleaned_text="hello",
        citation_string="A — T, §, ¶1",
        chunker_version="mvp-1",
    )
    db_session.add_all([source, work, passage])
    db_session.flush()
    return work.id, passage.id


def test_insert_passage_embeddings_idempotent_duplicate_skipped(db_session):
    work_id, passage_id = _seed_work_with_passage(db_session)
    vec = [0.01] * EMBEDDING_DIM
    row = {
        "id": uuid.uuid4(),
        "passage_id": passage_id,
        "work_id": work_id,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "embedding": vec,
    }
    insert_passage_embeddings_idempotent(db_session, [row])
    db_session.flush()
    insert_passage_embeddings_idempotent(db_session, [row])
    db_session.flush()

    n = db_session.scalar(
        select(func.count()).select_from(PassageEmbedding).where(PassageEmbedding.passage_id == passage_id)
    )
    assert n == 1


def test_embed_passages_second_pass_inserts_nothing(monkeypatch, db_session):
    work_id, passage_id = _seed_work_with_passage(db_session)

    def fake_encode(texts: list[str]) -> list[list[float]]:
        return [[0.02] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr("app.ingest.embed.encode_texts", fake_encode)

    n1 = embed_passages_for_work(db_session, work_id)
    db_session.flush()
    n2 = embed_passages_for_work(db_session, work_id)
    db_session.flush()

    assert n1 == 1
    assert n2 == 0
    assert (
        db_session.scalar(select(func.count()).select_from(PassageEmbedding).where(PassageEmbedding.passage_id == passage_id))
        == 1
    )
