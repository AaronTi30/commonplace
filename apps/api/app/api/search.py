from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, and_, func, or_, select

from app.api.errors import error
from app.db.deps import get_db_session
from app.db.models import Passage, PassageEmbedding, Source, SourceType, Work
from app.ingest.embed import EMBEDDING_MODEL, encode_texts
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api", tags=["search"])

SNIPPET_MAX = 300

EncodeQueryVector = Callable[[str], list[float]]


def snippet_from_cleaned(cleaned_text: str, max_len: int = SNIPPET_MAX) -> str:
    """First ``max_len`` chars of ``cleaned_text``, cut back to the previous word boundary."""
    if len(cleaned_text) <= max_len:
        return cleaned_text
    chunk = cleaned_text[:max_len]
    last_space = chunk.rfind(" ")
    if last_space > 0:
        return chunk[:last_space]
    return chunk


def get_encode_query_vector() -> EncodeQueryVector:
    def _encode(q: str) -> list[float]:
        vecs = encode_texts([q])
        return vecs[0]

    return _encode


class SearchFilters(BaseModel):
    source_type: list[str] | None = None
    author: list[str] | None = None
    work_ids: list[uuid.UUID] | None = None
    language: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    k: int = 10
    filters: SearchFilters | None = None


def _filter_conditions(filters: SearchFilters | None) -> list:
    if filters is None:
        return []
    conds: list = []

    if filters.source_type:
        st_conds = []
        for st in filters.source_type:
            try:
                st_conds.append(Source.source_type == SourceType(st))
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error("invalid_filter", "invalid source_type in filters", details=st),
                ) from e
        conds.append(or_(*st_conds))

    if filters.author:
        conds.append(or_(*[Work.author.ilike(f"%{a}%") for a in filters.author]))

    if filters.work_ids:
        conds.append(Work.id.in_(filters.work_ids))

    if filters.language:
        lang_conds = [func.lower(Work.language) == lang.lower() for lang in filters.language]
        conds.append(or_(*lang_conds))

    return conds


def _search_select(query_embedding: list[float], k: int, filters: SearchFilters | None) -> Select:
    dist = PassageEmbedding.embedding.cosine_distance(query_embedding)
    score_expr = (1 - dist).label("score")

    stmt = (
        select(
            Passage.id.label("passage_id"),
            Work.id.label("work_id"),
            Passage.citation_string,
            Passage.cleaned_text,
            score_expr,
        )
        .join(Passage, Passage.id == PassageEmbedding.passage_id)
        .join(Work, Work.id == PassageEmbedding.work_id)
        .join(Source, Source.id == Work.source_id)
        .where(PassageEmbedding.embedding_model == EMBEDDING_MODEL)
        .order_by(dist.asc())
        .limit(k)
    )
    fc = _filter_conditions(filters)
    if fc:
        stmt = stmt.where(and_(*fc))
    return stmt


def retrieve_passages_similarity(
    session: Session,
    query_embedding: list[float],
    k: int,
    filters: SearchFilters | None,
) -> list[dict[str, Any]]:
    """
    Top-k passages by cosine similarity (full ``cleaned_text``), for search + ask.
    """
    stmt = _search_select(query_embedding, k, filters)
    rows = session.execute(stmt).all()
    return [
        {
            "passage_id": str(r.passage_id),
            "work_id": str(r.work_id),
            "citation_string": r.citation_string,
            "cleaned_text": r.cleaned_text,
            "score": float(r.score),
        }
        for r in rows
    ]


@router.post("/search")
def search(
    body: SearchRequest,
    session: Session = Depends(get_db_session),
    encode_query_vector: EncodeQueryVector = Depends(get_encode_query_vector),
) -> dict:
    q = body.query.strip()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_query", "query must not be empty"),
        )
    if body.k < 1 or body.k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_k", "k must be between 1 and 50"),
        )

    q_vec = encode_query_vector(q)
    rows = retrieve_passages_similarity(session, q_vec, body.k, body.filters)

    results = [
        {
            "passage_id": r["passage_id"],
            "work_id": r["work_id"],
            "citation_string": r["citation_string"],
            "cleaned_text_snippet": snippet_from_cleaned(r["cleaned_text"]),
            "score": r["score"],
        }
        for r in rows
    ]

    return {
        "results": results,
        "meta": {"k": body.k, "embedding_model": EMBEDDING_MODEL},
    }


__all__ = [
    "EncodeQueryVector",
    "SearchFilters",
    "SearchRequest",
    "get_encode_query_vector",
    "retrieve_passages_similarity",
    "router",
    "snippet_from_cleaned",
]
