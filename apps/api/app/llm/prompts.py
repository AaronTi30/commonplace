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
    return f"""You answer questions using ONLY the source passages provided. Respond with a single JSON object — no markdown fences, no commentary, nothing else.

Schema:
{{"claims":[{{"claim":"string","supports":[{{"passage_id":"<uuid>","quote":"verbatim substring from that passage's text"}}]}}]}}

Rules:
- Each "quote" MUST be a verbatim substring copied exactly from the passage with that passage_id.
- Only use passage_id values that appear below.
- If you cannot ground every claim in the passages, return {{"claims":[]}}.

SOURCE PASSAGES:
{blocks}

QUESTION: {question}

JSON ANSWER:"""


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
    return f"""You are a helpful assistant that answers questions using only the provided source passages.

SOURCE PASSAGES:
{blocks}

QUESTION: {question}

INSTRUCTIONS:
- Answer the question directly and concisely.
- Use inline citations like [1], [2] referring to the passage numbers above.
- Every sentence that makes a claim must include at least one [N] citation.
- Do NOT use phrases like "Excerpt 1" — only [N] markers.
- If the passages do not contain enough information to answer, respond with: Insufficient evidence.

ANSWER:"""


def build_fluent_repair_prompt(question: str, passages: list[dict[str, Any]], previous: str) -> str:
    base = build_fluent_prompt(question, passages)
    return f"""Your previous answer was missing required [N] citations. Rewrite it with proper [N] citations.

Previous output (missing citations):
{previous}

{base}"""
