from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest.normalize import normalize_newlines

# Pinned chunker version for deterministic regression tests + DB `chunker_version`.
CHUNKER_VERSION = "mvp-1"

_MERGE_MAX_CHARS = 1800
_SENTENCE_SPLIT_LOW = 1200
_SENTENCE_SPLIT_HIGH = 1800

_CHAPTER_HEADING = re.compile(
    r"^(Chapter|Book|Part|Section|Canto|Act|Scene)\s+[\dIVXLCivxlc]+(?:\s*(?:[—:])\s*.+)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PassageChunk:
    section_label: str | None
    passage_index: int
    cleaned_text: str
    citation_string: str
    chunker_version: str


def _clean_para(text: str) -> str:
    t = text.strip()
    return re.sub(r"\s+", " ", t)


def _all_caps_heading(trimmed: str) -> bool:
    if not (3 <= len(trimmed) <= 60):
        return False
    has_letter = False
    for c in trimmed:
        if c.isalpha():
            has_letter = True
            if not c.isupper():
                return False
    return has_letter


def _try_heading(lines: list[str], i: int) -> str | None:
    trimmed = lines[i].strip()
    if not trimmed:
        return None
    prev_blank = i == 0 or not lines[i - 1].strip()

    if prev_blank and _all_caps_heading(trimmed):
        return trimmed

    if _CHAPTER_HEADING.match(trimmed):
        return trimmed

    followed_blank = i + 1 < len(lines) and not lines[i + 1].strip()
    if (
        prev_blank
        and followed_blank
        and len(trimmed) <= 60
        and not trimmed.endswith(".")
        and not trimmed.endswith(",")
    ):
        return trimmed

    return None


def _paragraphs_with_sections(text: str) -> list[tuple[str | None, str]]:
    lines = normalize_newlines(text).split("\n")
    section: str | None = None
    out: list[tuple[str | None, str]] = []
    cur: list[str] = []

    def flush_cur() -> None:
        nonlocal cur
        if not cur:
            return
        block = "\n".join(cur).strip()
        cur = []
        if not block:
            return
        for para in re.split(r"\n\n+", block):
            p = _clean_para(para)
            if p:
                out.append((section, p))

    i = 0
    while i < len(lines):
        if not lines[i].strip():
            flush_cur()
            i += 1
            continue
        label = _try_heading(lines, i)
        if label is not None:
            flush_cur()
            section = label
            i += 1
            continue
        cur.append(lines[i])
        i += 1
    flush_cur()
    return out


def _split_long_paragraph(p: str) -> list[str]:
    if len(p) <= _MERGE_MAX_CHARS:
        return [p]
    parts: list[str] = []
    rest = p
    while len(rest) > _MERGE_MAX_CHARS:
        window = rest[:_MERGE_MAX_CHARS]
        best = -1
        for m in re.finditer(r"[.!?]\s+", window):
            e = m.end()
            if _SENTENCE_SPLIT_LOW <= e <= _SENTENCE_SPLIT_HIGH:
                best = max(best, e)
        if best < 0:
            parts.append(rest[:_MERGE_MAX_CHARS])
            rest = rest[_MERGE_MAX_CHARS:]
        else:
            parts.append(rest[:best])
            rest = rest[best:]
    if rest:
        parts.append(rest)
    return parts


def _expand_long_paragraphs(
    paras: list[tuple[str | None, str]],
) -> list[tuple[str | None, str]]:
    expanded: list[tuple[str | None, str]] = []
    for sec, p in paras:
        for part in _split_long_paragraph(p):
            expanded.append((sec, part))
    return expanded


def _merge_paragraphs(expanded: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    if not expanded:
        return []
    merged: list[tuple[str | None, str]] = []
    acc_sec, acc_parts = expanded[0][0], [expanded[0][1]]
    for sec, p in expanded[1:]:
        candidate = "\n\n".join(acc_parts + [p])
        if len(candidate) <= _MERGE_MAX_CHARS:
            acc_parts.append(p)
            continue
        merged.append((acc_sec, "\n\n".join(acc_parts)))
        acc_sec, acc_parts = sec, [p]
    merged.append((acc_sec, "\n\n".join(acc_parts)))
    return merged


def _citation(author: str | None, title: str | None, section_label: str | None, passage_index: int) -> str:
    au = author if author else "Unknown"
    ti = title if title else "Unknown"
    sl = section_label if section_label else "§"
    return f"{au} — {ti}, {sl}, ¶{passage_index}"


def chunk_normalized_text(
    normalized_text: str,
    *,
    author: str | None,
    title: str | None,
    chunker_version: str = CHUNKER_VERSION,
) -> list[PassageChunk]:
    """
    Deterministic passage segmentation on already-normalized plain text.

    Callers run ``normalize_*`` first (Gutenberg boilerplate / Wikisource HTML).
    """
    text = normalized_text.strip()
    if not text:
        return []

    paras = _paragraphs_with_sections(text)
    expanded = _expand_long_paragraphs(paras)
    merged = _merge_paragraphs(expanded)

    out: list[PassageChunk] = []
    passage_index = 0
    for sec, body in merged:
        cleaned = _clean_para(body)
        if not cleaned:
            continue
        passage_index += 1
        cite = _citation(author, title, sec, passage_index)
        out.append(
            PassageChunk(
                section_label=sec,
                passage_index=passage_index,
                cleaned_text=cleaned,
                citation_string=cite,
                chunker_version=chunker_version,
            )
        )
    return out
