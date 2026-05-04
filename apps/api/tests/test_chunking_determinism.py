from __future__ import annotations

from app.ingest.chunk import CHUNKER_VERSION, PassageChunk, chunk_normalized_text
from app.ingest.normalize import normalize_gutenberg_plaintext, normalize_wikisource_html


def _chunks_key(chunks: list[PassageChunk]) -> list[tuple]:
    return [
        (c.passage_index, c.section_label, c.cleaned_text, c.citation_string, c.chunker_version)
        for c in chunks
    ]


def test_chunking_identical_runs_same_output():
    text = "First paragraph here.\n\nSecond paragraph follows.\n\nThird is last."
    a = chunk_normalized_text(text, author="Plato", title="Republic", chunker_version=CHUNKER_VERSION)
    b = chunk_normalized_text(text, author="Plato", title="Republic", chunker_version=CHUNKER_VERSION)
    assert _chunks_key(a) == _chunks_key(b)


def test_paragraph_split_on_blank_lines():
    # Long segments so the merge stage does not combine distinct blank-line paragraphs.
    text = "x" * 1000 + "\n\n" + "y" * 1000 + "\n\n" + "z" * 1000
    chunks = chunk_normalized_text(text, author="A", title="T", chunker_version=CHUNKER_VERSION)
    assert [c.cleaned_text for c in chunks] == ["x" * 1000, "y" * 1000, "z" * 1000]
    assert [c.passage_index for c in chunks] == [1, 2, 3]


def test_merge_small_paragraphs_up_to_merge_max():
    # Each segment is 100 'a'; merge with "\n\n" (2 chars) between parts.
    paras = ["a" * 100] * 18
    text = "\n\n".join(paras)
    chunks = chunk_normalized_text(text, author="A", title="T", chunker_version=CHUNKER_VERSION)
    assert len(chunks) == 2
    assert len(chunks[0].cleaned_text) <= 1800
    assert len(chunks[1].cleaned_text) <= 1800
    assert "".join(c.cleaned_text.replace(" ", "") for c in chunks) == "a" * 1800


def test_split_long_paragraph_at_sentence_boundary_in_window():
    # First chunk should break at ". " with end position in [1200, 1800].
    prefix = "w" * 1298
    rest = "y" * 700
    long_para = f"{prefix}. {rest}"
    text = long_para
    chunks = chunk_normalized_text(text, author="A", title="T", chunker_version=CHUNKER_VERSION)
    assert len(chunks) >= 2
    assert 1200 <= len(chunks[0].cleaned_text) <= 1800
    assert "." in chunks[0].cleaned_text


def test_split_long_paragraph_hard_split_without_sentence():
    long_para = "z" * 2500
    chunks = chunk_normalized_text(long_para, author="A", title="T", chunker_version=CHUNKER_VERSION)
    assert len(chunks) >= 2
    assert len(chunks[0].cleaned_text) == 1800
    assert "".join(c.cleaned_text for c in chunks) == long_para


def test_heading_all_caps_book():
    text = "\n\nBOOK I\n\nAlpha beta.\n\nGamma delta."
    chunks = chunk_normalized_text(text, author="Homer", title="Iliad", chunker_version=CHUNKER_VERSION)
    assert chunks[0].section_label == "BOOK I"
    assert "BOOK I" in chunks[0].citation_string
    assert "Alpha beta." in chunks[0].cleaned_text or chunks[0].cleaned_text.startswith("Alpha")


def test_heading_chapter_pattern_mixed_case():
    text = "Chapter 2 — The debate\n\nBody text one.\n\nBody text two."
    chunks = chunk_normalized_text(text, author="A", title="T", chunker_version=CHUNKER_VERSION)
    assert chunks[0].section_label == "Chapter 2 — The debate"
    assert chunks[0].cleaned_text.startswith("Body text one.")


def test_heading_short_line_surrounded_by_blanks_not_sentence_ending():
    text = "\n\nShort title here\n\nNot a heading line ends with period.\n\nNext para."
    chunks = chunk_normalized_text(text, author="A", title="T", chunker_version=CHUNKER_VERSION)
    labels = [c.section_label for c in chunks]
    assert "Short title here" in labels


def test_citation_uses_section_placeholder():
    text = "Only body.\n\nMore body."
    chunks = chunk_normalized_text(text, author="Auth", title="Work", chunker_version=CHUNKER_VERSION)
    for c in chunks:
        assert "§" in c.citation_string
        assert "Auth — Work" in c.citation_string


def test_normalize_gutenberg_strips_boilerplate():
    raw = """*** START OF THE PROJECT GUTENBERG EBOOK DEMO ***

Hello from the book.

*** END OF THE PROJECT GUTENBERG EBOOK DEMO ***
"""
    normalized = normalize_gutenberg_plaintext(raw)
    assert "Hello from the book." in normalized
    assert "START OF THE PROJECT GUTENBERG" not in normalized
    assert "END OF THE PROJECT GUTENBERG" not in normalized


def test_normalize_wikisource_html_deterministic():
    html = '<div><p>Hello <b>world</b>.</p><br/><script>x()</script><p>Second &amp; line.</p></div>'
    a = normalize_wikisource_html(html)
    b = normalize_wikisource_html(html)
    assert a == b
    assert "Hello world." in a
    assert "Second & line." in a
    assert "script" not in a.lower()


def test_pipeline_normalize_then_chunk_is_deterministic():
    raw = """*** START OF THE PROJECT GUTENBERG EBOOK X ***

Para one.

Para two.

*** END OF THE PROJECT GUTENBERG EBOOK X ***
"""
    n = normalize_gutenberg_plaintext(raw)
    c1 = chunk_normalized_text(n, author="A", title="B", chunker_version="test-v1")
    c2 = chunk_normalized_text(n, author="A", title="B", chunker_version="test-v1")
    assert _chunks_key(c1) == _chunks_key(c2)
    assert all(c.chunker_version == "test-v1" for c in c1)


def test_different_chunker_version_recorded():
    text = "Single."
    c = chunk_normalized_text(text, author="A", title="T", chunker_version="other")
    assert c[0].chunker_version == "other"
