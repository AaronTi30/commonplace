from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.api.errors import error
from app.db.deps import get_db_session
from app.db.models import Passage, PassageEmbedding, ReadingProgress, Source, SourceArtifact, SourceType, Work

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["works"])


class PatchWorkBody(BaseModel):
    title: str | None = Field(default=None)
    author: str | None = Field(default=None)
    language: str | None = Field(default=None)


class ProgressBody(BaseModel):
    position: str


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

    source = session.get(Source, work.source_id)

    return {
        "work": {
            "work_id": work.id,
            "title": work.title,
            "author": work.author,
            "language": work.language,
            "source_type": source.source_type.value if source else None,
            "ingestion_state": work.ingestion_state.value,
            "ingested_at": work.ingested_at,
            "created_at": work.created_at,
            "updated_at": work.updated_at,
        },
        "passages": passages,
        **({"next_cursor": next_cursor} if next_cursor else {}),
    }


def _work_list_row_dict(work: Work, source: Source) -> dict:
    return {
        "work_id": work.id,
        "title": work.title,
        "author": work.author,
        "language": work.language,
        "source_type": source.source_type.value,
        "ingestion_state": work.ingestion_state.value,
        "ingested_at": work.ingested_at,
        "created_at": work.created_at,
    }


@router.patch("/works/{work_id}")
def patch_work(
    work_id: uuid.UUID,
    body: PatchWorkBody,
    session: Session = Depends(get_db_session),
) -> dict:
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(work, key, value)
    session.flush()

    source = session.get(Source, work.source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error("server_error", "work has no source"))
    return {"work": _work_list_row_dict(work, source)}


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
    source = session.get(Source, source_id)
    if source and source.source_type in (SourceType.epub, SourceType.pdf):
        artifact = session.scalar(
            select(SourceArtifact)
            .where(SourceArtifact.source_id == source.id)
            .order_by(SourceArtifact.created_at.desc())
            .limit(1)
        )
        if artifact and artifact.raw_file_path:
            fp = artifact.raw_file_path
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                parent = os.path.dirname(fp)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            except OSError as exc:
                logger.warning("upload file cleanup failed for %s: %s", fp, exc)

    # Delete child rows first. `passage_embeddings.work_id` is a RESTRICT FK, so we must
    # remove embeddings (or passages which cascade to embeddings) before deleting Work.
    session.execute(delete(PassageEmbedding).where(PassageEmbedding.work_id == work_id))
    session.execute(delete(Passage).where(Passage.work_id == work_id))
    session.execute(delete(Work).where(Work.id == work_id))
    session.execute(delete(Source).where(Source.id == source_id))
    session.flush()

    return {"deleted": True, "work_id": str(work_id)}


@router.get("/works/{work_id}/file")
def get_work_file(work_id: uuid.UUID, session: Session = Depends(get_db_session)):
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))

    source = session.get(Source, work.source_id)
    if source is None or source.source_type not in (SourceType.epub, SourceType.pdf):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error("file_not_available", "this work has no uploaded file"),
        )

    artifact = session.scalar(
        select(SourceArtifact)
        .where(SourceArtifact.source_id == source.id)
        .order_by(SourceArtifact.created_at.desc())
        .limit(1)
    )
    if artifact is None or not artifact.raw_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error("file_not_found", "file path not recorded"),
        )
    if not os.path.isfile(artifact.raw_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error("file_not_found", "file not found on disk"),
        )

    media_type = (
        "application/epub+zip"
        if artifact.raw_file_path.lower().endswith(".epub")
        else "application/pdf"
    )
    return FileResponse(artifact.raw_file_path, media_type=media_type)


@router.get("/works/{work_id}/progress")
def get_reading_progress(work_id: uuid.UUID, session: Session = Depends(get_db_session)) -> dict:
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))
    progress = session.get(ReadingProgress, work_id)
    return {"position": progress.position if progress else None}


@router.put("/works/{work_id}/progress")
def put_reading_progress(
    work_id: uuid.UUID,
    body: ProgressBody,
    session: Session = Depends(get_db_session),
) -> dict:
    work = session.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error("not_found", "work not found"))
    progress = session.get(ReadingProgress, work_id)
    if progress:
        progress.position = body.position
        progress.updated_at = datetime.now(timezone.utc)
    else:
        session.add(ReadingProgress(work_id=work_id, position=body.position))
    session.flush()
    return {"position": body.position}
