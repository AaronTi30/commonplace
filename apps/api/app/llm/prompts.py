from __future__ import annotations

from typing import Any


def _format_passage_block(p: dict[str, Any], index: int) -> str:
    return (
        f"### Context [{index}]\n"
        f"passage_id: {p['passage_id']}\n"
        f"citation: {p['citation_string']}\n\n"
        f"{p['cleaned_text']}\n"
    )


def build_strict_prompt(question: str, passages: list[dict[str, Any]]) -> str:
    blocks = "\n".join(_format_passage_block(p, i) for i, p in enumerate(passages, start=1))
    return f"""You answer using ONLY the passages below. Respond with a single JSON object (no markdown fences, no commentary).

Schema:
{{"claims":[{{"claim":"string","supports":[{{"passage_id":"<uuid>","quote":"verbatim substring from that passage's text"}}]}}]}}

Rules:
- Each "quote" MUST be copied verbatim from the passage matching passage_id (can be a substring).
- Only use passage_id values that appear in the context.
- If you cannot ground claims in the passages, return {{"claims":[]}}.

Question: {question}

{blocks}
"""


def build_strict_repair_prompt(
    question: str,
    passages: list[dict[str, Any]],
    previous_response: str,
    validation_errors: list[str],
) -> str:
    base = build_strict_prompt(question, passages)
    err_txt = "\n".join(f"- {e}" for e in validation_errors)
    return f"""Your previous answer failed validation. Fix it and output ONLY valid JSON for the same schema.

Validation errors:
{err_txt}

Previous output (invalid):
{previous_response}

{base}
"""


def build_fluent_prompt(question: str, passages: list[dict[str, Any]]) -> str:
    blocks = "\n".join(_format_passage_block(p, i) for i, p in enumerate(passages, start=1))
    return f"""You are a helpful assistant. Answer the question using the numbered passages below.

Citation rules (MANDATORY):
- Use inline numeric citations like [1], [2] that refer to the passage numbers below.
- Do NOT write \"Excerpt 1\" or similar text; ONLY use [N] markers.
- Every paragraph must contain at least one [N] citation.
- If you cannot answer from the passages, respond with: Insufficient evidence. [1]

Question: {question}

{blocks}
"""


def build_fluent_repair_prompt(question: str, passages: list[dict[str, Any]], previous: str) -> str:
    base = build_fluent_prompt(question, passages)
    return f"""You forgot to include required [N] citations. Rewrite your answer and include [N] citations.

Previous output (invalid):
{previous}

{base}
"""
