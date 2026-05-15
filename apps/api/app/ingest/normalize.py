from __future__ import annotations

import html
import re


def normalize_newlines(text: str) -> str:
    """Normalize CRLF / lone CR to ``\\n`` (chunker paragraph contract)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_gutenberg_boilerplate(text: str) -> str:
    """
    Remove standard Project Gutenberg header/footer blocks (MVP, line-based).

    Cuts from the first line containing a START marker through content before
    the first line containing an END marker.
    """
    lines = normalize_newlines(text).split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        upper = line.upper()
        if "START OF THE PROJECT GUTENBERG EBOOK" in upper or "START OF THIS PROJECT GUTENBERG EBOOK" in upper:
            start_idx = i + 1
            break
    end_idx = len(lines)
    for j in range(start_idx, len(lines)):
        upper = lines[j].upper()
        if "END OF THE PROJECT GUTENBERG EBOOK" in upper or "END OF THIS PROJECT GUTENBERG EBOOK" in upper:
            end_idx = j
            break
    return "\n".join(lines[start_idx:end_idx]).strip()


def strip_gutenberg_markup(text: str) -> str:
    """Remove plain text markup conventions used in Gutenberg files."""
    # _italics_ → italics
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # superscripts like M^{rs} → Mrs or M^r → Mr
    text = re.sub(r"\^\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\^(\w)", r"\1", text)
    return text


def normalize_gutenberg_plaintext(raw: str) -> str:
    """Strip Gutenberg boilerplate; normalize newlines (spec: normalize before chunk)."""
    t = normalize_newlines(raw)
    t = strip_gutenberg_boilerplate(t)
    t = strip_gutenberg_markup(t)
    return t.strip()


_WS_COLLAPSE = re.compile(r"[ \t]+")
_MULTI_BLANK = re.compile(r"\n{3,}")


def normalized_plaintext_for_chunking(raw: str, source_type: str) -> str:
    """
    Route raw artifact bytes to the correct normalizer before chunking.

    ``source_type`` is ``\"gutenberg\"``, ``\"wikisource\"``, ``\"epub\"``, or ``\"pdf\"``
    (enum value strings). EPUB/PDF are normalized in the worker via extractors; this
    entrypoint is only used for remote fetch payloads.
    """
    if source_type == "gutenberg":
        return normalize_gutenberg_plaintext(raw)
    if source_type == "wikisource":
        return normalize_wikisource_html(raw)
    if source_type in {"epub", "pdf"}:
        raise ValueError("epub/pdf plaintext is produced by extract_epub_text / extract_pdf_text")
    raise ValueError(f"unsupported source_type: {source_type!r}")


def normalize_wikisource_html(raw_html: str) -> str:
    """
    Deterministic HTML → text for English Wikisource REST HTML (MVP, pinned).

    Rules: drop ``script``/``style``, map common block breaks to ``\\n``,
    strip remaining tags, ``html.unescape``, collapse horizontal whitespace,
    cap consecutive newlines at two.
    """
    t = normalize_newlines(raw_html)
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", "", t)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", "", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</\s*(p|div|tr|h[1-6])\s*>", "\n", t)
    t = re.sub(r"(?i)<\s*p[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = _WS_COLLAPSE.sub(" ", t)
    t = _MULTI_BLANK.sub("\n\n", t)
    return t.strip()
