from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ValidationError


class SupportRef(BaseModel):
    passage_id: str
    quote: str


class ClaimBlock(BaseModel):
    claim: str
    supports: list[SupportRef]


class StrictAnswer(BaseModel):
    claims: list[ClaimBlock]


def normalize_for_quote_validation(text: str) -> str:
    """Normalize passage/quote text for substring checks (spec: NFC, whitespace, quotes, dashes, footnotes, case-fold)."""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2014", "-").replace("\u2013", "-")
    t = re.sub(r"\[\d+\]", "", t)
    t = re.sub(r"\(\d+\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.casefold()


def extract_json_object(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if "```" in t:
        start = t.find("```")
        block = t[start + 3 :]
        nl = block.find("\n")
        if nl != -1 and block[:nl].strip().lower().startswith("json"):
            block = block[nl + 1 :]
        end = block.rfind("```")
        if end != -1:
            block = block[:end]
        t = block.strip()
    i = t.find("{")
    j = t.rfind("}")
    if i == -1 or j < i:
        return None
    try:
        return json.loads(t[i : j + 1])
    except json.JSONDecodeError:
        return None


def parse_strict_answer(llm_text: str) -> StrictAnswer | None:
    raw = extract_json_object(llm_text)
    if raw is None:
        return None
    try:
        return StrictAnswer.model_validate(raw)
    except ValidationError:
        return None


def validate_strict_answer(
    answer: StrictAnswer,
    passages_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return human-readable errors; empty list means all quotes are grounded in the cited passages."""
    errors: list[str] = []
    for ci, claim in enumerate(answer.claims):
        for si, sup in enumerate(claim.supports):
            ref = passages_by_id.get(sup.passage_id)
            if ref is None:
                errors.append(f"claim[{ci}] support[{si}]: unknown passage_id {sup.passage_id!r}")
                continue
            cleaned = ref["cleaned_text"]
            nq = normalize_for_quote_validation(sup.quote)
            nc = normalize_for_quote_validation(cleaned)
            if nq not in nc:
                errors.append(
                    f"claim[{ci}] support[{si}]: quote not found in passage {sup.passage_id}"
                )
    return errors


def render_strict_markdown(answer: StrictAnswer, passages_by_id: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, claim in enumerate(answer.claims, start=1):
        parts.append(f"### Claim {i}\n\n{claim.claim}\n")
        for sup in claim.supports:
            cite = (
                passages_by_id.get(sup.passage_id, {}).get("citation_string")
                or sup.passage_id
            )
            parts.append(f'\n> "{sup.quote}"\n> — {cite}\n')
    return "\n".join(parts).strip()


INSUFFICIENT_EVIDENCE_MARKDOWN = (
    "**Insufficient evidence.** The model output could not be grounded in the retrieved passages."
)


def cited_passage_ids_strict(answer: StrictAnswer) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for claim in answer.claims:
        for sup in claim.supports:
            if sup.passage_id not in seen:
                seen.add(sup.passage_id)
                out.append(sup.passage_id)
    return out


_FLUENT_CITE_RE = re.compile(r"\[(\d+)\]")


def cited_passage_ids_from_fluent_markdown(markdown: str, retrieved_passages: list[dict[str, Any]]) -> list[str]:
    """Map ``[N]`` markers to the Nth retrieved passage (1-based), first occurrence order, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _FLUENT_CITE_RE.finditer(markdown):
        idx = int(m.group(1))
        if 1 <= idx <= len(retrieved_passages):
            pid = retrieved_passages[idx - 1]["passage_id"]
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
    return out
