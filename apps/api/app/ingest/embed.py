from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import Passage, PassageEmbedding

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
_ENCODE_BATCH = 32

_model_lock = threading.Lock()
_model = None


def get_sentence_transformer():
    """Lazy singleton (worker may import embed without immediately loading weights)."""
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Encode texts to 384-dim cosine-normalized vectors (pinned MiniLM)."""
    if not texts:
        return []
    model = get_sentence_transformer()
    vectors = model.encode(
        texts,
        batch_size=_ENCODE_BATCH,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return [v.astype("float32").tolist() for v in vectors]


def insert_passage_embeddings_idempotent(session: Session, rows: Sequence[dict]) -> None:
    """Insert embedding rows; skip duplicates per (passage_id, embedding_model)."""
    if not rows:
        return
    stmt = (
        pg_insert(PassageEmbedding.__table__)
        .values(list(rows))
        .on_conflict_do_nothing(constraint="uq_passage_embeddings_passage_model")
    )
    session.execute(stmt)


def embed_passages_for_work(
    session: Session,
    work_id: uuid.UUID,
    *,
    encode_fn: Callable[[list[str]], list[list[float]]] | None = None,
) -> int:
    """
    Embed passages for ``work_id`` that lack ``EMBEDDING_MODEL`` rows.

    Returns the number of passages processed (embeddings computed this call).
    """
    encode_fn = encode_fn or encode_texts

    exists_emb = (
        exists()
        .where(PassageEmbedding.passage_id == Passage.id)
        .where(PassageEmbedding.embedding_model == EMBEDDING_MODEL)
    )
    stmt = (
        select(Passage)
        .where(Passage.work_id == work_id)
        .where(~exists_emb)
        .order_by(Passage.passage_index)
    )
    missing = list(session.scalars(stmt))
    if not missing:
        return 0

    inserted = 0
    for i in range(0, len(missing), _ENCODE_BATCH):
        batch = missing[i : i + _ENCODE_BATCH]
        texts = [p.cleaned_text for p in batch]
        vectors = encode_fn(texts)
        if len(vectors) != len(batch):
            raise RuntimeError("encode_fn returned wrong number of vectors")
        rows = [
            {
                "id": uuid.uuid4(),
                "passage_id": p.id,
                "work_id": p.work_id,
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dim": EMBEDDING_DIM,
                "embedding": vec,
            }
            for p, vec in zip(batch, vectors, strict=True)
        ]
        insert_passage_embeddings_idempotent(session, rows)
        inserted += len(rows)
    return inserted
