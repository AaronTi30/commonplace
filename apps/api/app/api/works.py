from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db.models import SourceType
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.api.errors import error
from app.db.deps import get_db_session
from app.db.models import Passage, PassageEmbedding, Source, Work

router = APIRouter(prefix="/api", tags=["works"])


@router.get("/works")
def list_works(
    session: Session = Depends(get_db_session),
    source_type: str | None = None,
    author: str | None = None,
    title: str | None = None,
) -> dict:
    stmt = select(Work, Source).join(Source, Work.source_id == Source.id)
    conds = []
    if source_type:
        try:
            conds.append(Source.source_type == SourceType(source_type))
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error("invalid_source_type", "invalid source_type"),
            ) from e
    if author:
        conds.append(Work.author.ilike(f"%{author}%"))
    if title:
        conds.append(Work.title.ilike(f"%{title}%"))
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(Work.created_at.desc())

    rows = session.execute(stmt).all()
    works = []
    for work, source in rows:
        works.append(
            {
                "work_id": work.id,
                "title": work.title,
                "author": work.author,
                "language": work.language,
                "source_type": source.source_type.value,
                "ingestion_state": work.ingestion_state.value,
                "ingested_at": work.ingested_at,
                "created_at": work.created_at,
            }
        )
    return {"works": works}


@router.get("/works/{work_id}")
def get_work(
    work_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))

    after = 0
    if cursor:
        try:
            after = int(cursor)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error("invalid_cursor", "cursor must be an integer")
            ) from e

    stmt = (
        select(Passage)
        .where(Passage.work_id == work_id)
        .where(Passage.passage_index > after)
        .order_by(Passage.passage_index.asc())
        .limit(limit + 1)
    )
    passages_all = list(session.scalars(stmt))
    has_more = len(passages_all) > limit
    passages_page = passages_all[:limit]

    passages = [
        {
            "passage_id": p.id,
            "passage_index": p.passage_index,
            "section_label": p.section_label,
            "cleaned_text": p.cleaned_text,
            "citation_string": p.citation_string,
        }
        for p in passages_page
    ]

    next_cursor = str(passages_page[-1].passage_index) if has_more and passages_page else None

    return {
        "work": {
            "work_id": work.id,
            "title": work.title,
            "author": work.author,
            "language": work.language,
            "ingestion_state": work.ingestion_state.value,
            "ingested_at": work.ingested_at,
            "created_at": work.created_at,
            "updated_at": work.updated_at,
        },
        "passages": passages,
        **({"next_cursor": next_cursor} if next_cursor else {}),
    }


@router.delete("/works/{work_id}")
def delete_work(work_id: uuid.UUID, session: Session = Depends(get_db_session)) -> dict:
    """
    Delete a work from the corpus.

    Deletes the Work row (cascades to passages, embeddings, and ingestion jobs),
    then deletes its Source row (cascades to source_artifacts). One-work-per-source
    is enforced by schema, so this is safe.
    """
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))

    source_id = work.source_id

    # Delete child rows first. `passage_embeddings.work_id` is a RESTRICT FK, so we must
    # remove embeddings (or passages which cascade to embeddings) before deleting Work.
    session.execute(delete(PassageEmbedding).where(PassageEmbedding.work_id == work_id))
    session.execute(delete(Passage).where(Passage.work_id == work_id))
    session.execute(delete(Work).where(Work.id == work_id))
    session.execute(delete(Source).where(Source.id == source_id))
    session.flush()

    return {"deleted": True, "work_id": str(work_id)}
