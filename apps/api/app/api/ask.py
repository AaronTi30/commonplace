from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.errors import error
from app.api.search import (
    EncodeQueryVector,
    SearchFilters,
    get_encode_query_vector,
    retrieve_passages_similarity,
)
from app.db.deps import get_db_session
from app.ingest.embed import EMBEDDING_MODEL
from app.llm.grounding import (
    INSUFFICIENT_EVIDENCE_MARKDOWN,
    cited_passage_ids_from_fluent_markdown,
    cited_passage_ids_strict,
    parse_strict_answer,
    render_strict_markdown,
    validate_strict_answer,
)
from app.llm.ollama_client import OllamaClient, get_ollama_client
from app.llm.prompts import (
    build_fluent_prompt,
    build_fluent_repair_prompt,
    build_strict_prompt,
    build_strict_repair_prompt,
)
from app.settings import settings

router = APIRouter(prefix="/api", tags=["ask"])


class AskMode(str, Enum):
    strict = "strict"
    fluent = "fluent"


class AskRequest(BaseModel):
    query: str
    k: int = 5
    mode: AskMode = AskMode.strict
    filters: SearchFilters | None = None


def _strict_flow(
    *,
    question: str,
    retrieved: list[dict[str, Any]],
    ollama: OllamaClient,
) -> tuple[str, list[str], dict[str, Any]]:
    passages_by_id = {p["passage_id"]: p for p in retrieved}
    prompt1 = build_strict_prompt(question, retrieved)
    out1 = ollama.generate(prompt1)
    parsed1 = parse_strict_answer(out1)
    errs1: list[str] = []
    if parsed1 is None:
        errs1 = ["Response was not valid JSON matching the strict schema."]
    else:
        errs1 = validate_strict_answer(parsed1, passages_by_id)

    if not errs1 and parsed1 is not None:
        md = render_strict_markdown(parsed1, passages_by_id)
        cited = cited_passage_ids_strict(parsed1)
        return md, cited, {"passed": True, "attempts": 1}

    repair = build_strict_repair_prompt(question, retrieved, out1, errs1)
    out2 = ollama.generate(repair)
    parsed2 = parse_strict_answer(out2)
    errs2: list[str] = []
    if parsed2 is None:
        errs2 = ["Response was not valid JSON matching the strict schema."]
    else:
        errs2 = validate_strict_answer(parsed2, passages_by_id)

    if not errs2 and parsed2 is not None:
        md = render_strict_markdown(parsed2, passages_by_id)
        cited = cited_passage_ids_strict(parsed2)
        return md, cited, {"passed": True, "attempts": 2}

    return (
        INSUFFICIENT_EVIDENCE_MARKDOWN,
        [],
        {"passed": False, "attempts": 2},
    )


@router.post("/ask")
def ask(
    body: AskRequest,
    session: Session = Depends(get_db_session),
    encode_query_vector: EncodeQueryVector = Depends(get_encode_query_vector),
    ollama: OllamaClient = Depends(get_ollama_client),
) -> dict[str, Any]:
    q = body.query.strip()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_query", "query must not be empty"),
        )
    if body.k < 1 or body.k > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_k", "k must be between 1 and 20 for /api/ask"),
        )

    q_vec = encode_query_vector(q)
    retrieved = retrieve_passages_similarity(session, q_vec, body.k, body.filters)

    ts = datetime.now(timezone.utc).isoformat()
    base_meta: dict[str, Any] = {
        "k": body.k,
        "mode": body.mode.value,
        "embedding_model": EMBEDDING_MODEL,
        "llm_model": settings.ollama_model,
        "timestamp": ts,
    }
    if body.filters is not None:
        base_meta["filters"] = body.filters.model_dump(mode="json")

    if body.mode == AskMode.strict:
        answer_markdown, cited_ids, strict_meta = _strict_flow(
            question=q, retrieved=retrieved, ollama=ollama
        )
        return {
            "answer_markdown": answer_markdown,
            "retrieved_passages": retrieved,
            "cited_passage_ids": cited_ids,
            "meta": {**base_meta, "strict_validation": strict_meta},
        }

    # fluent
    prompt = build_fluent_prompt(q, retrieved)
    answer_markdown = ollama.generate(prompt)
    cited = cited_passage_ids_from_fluent_markdown(answer_markdown, retrieved)
    if not cited:
        repair = build_fluent_repair_prompt(q, retrieved, answer_markdown)
        answer_markdown = ollama.generate(repair)
        cited = cited_passage_ids_from_fluent_markdown(answer_markdown, retrieved)
    return {
        "answer_markdown": answer_markdown,
        "retrieved_passages": retrieved,
        "cited_passage_ids": cited,
        "meta": base_meta,
    }


@router.post("/ask/stream")
async def ask_stream(
    body: AskRequest,
    session: Session = Depends(get_db_session),
    encode_query_vector: EncodeQueryVector = Depends(get_encode_query_vector),
    ollama: OllamaClient = Depends(get_ollama_client),
) -> StreamingResponse:
    """Stream a fluent-mode answer as Server-Sent Events."""
    q = body.query.strip()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_query", "query must not be empty"),
        )
    if body.k < 1 or body.k > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error("invalid_k", "k must be between 1 and 20 for /api/ask/stream"),
        )

    q_vec = encode_query_vector(q)
    retrieved = retrieve_passages_similarity(session, q_vec, body.k, body.filters)
    prompt = build_fluent_prompt(q, retrieved)

    ts = datetime.now(timezone.utc).isoformat()
    base_meta: dict[str, Any] = {
        "k": body.k,
        "mode": "fluent",
        "embedding_model": EMBEDDING_MODEL,
        "llm_model": settings.ollama_model,
        "timestamp": ts,
    }
    if body.filters is not None:
        base_meta["filters"] = body.filters.model_dump(mode="json")

    async def generate():
        yield f"data: {_json.dumps({'type': 'passages', 'retrieved_passages': retrieved, 'meta': base_meta})}\n\n"
        accumulated: list[str] = []
        try:
            async for token in ollama.stream_generate(prompt):
                accumulated.append(token)
                yield f"data: {_json.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as exc:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        full_text = "".join(accumulated)
        cited = cited_passage_ids_from_fluent_markdown(full_text, retrieved)
        yield f"data: {_json.dumps({'type': 'done', 'cited_passage_ids': cited, 'meta': base_meta})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
