from __future__ import annotations

import pytest

from app.ingest.canonicalize import canonicalize_gutenberg, canonicalize_wikisource


def test_gutenberg_bare_id():
    c = canonicalize_gutenberg("1342")
    assert c.locator == "1342"
    assert c.canonical_url == "https://www.gutenberg.org/ebooks/1342"


def test_gutenberg_ebooks_url():
    c = canonicalize_gutenberg("https://www.gutenberg.org/ebooks/1342/")
    assert c.locator == "1342"


def test_gutenberg_files_url():
    c = canonicalize_gutenberg("https://www.gutenberg.org/files/1342/1342-0.txt")
    assert c.locator == "1342"


def test_wikisource_spec_example_strip_query_fragment():
    c = canonicalize_wikisource(
        "http://en.wikisource.org/wiki/Republic?oldformat=true#Book_I",
    )
    assert c.locator == "https://en.wikisource.org/wiki/Republic"
    assert c.canonical_url == c.locator


def test_wikisource_nested_title_unchanged():
    url = "https://en.wikisource.org/wiki/Bhagavad_Gita/Chapter_1"
    c = canonicalize_wikisource(url)
    assert c.locator == url


def test_wikisource_https_spaces_to_underscores():
    c = canonicalize_wikisource("https://en.wikisource.org/wiki/Some%20Page")
    assert c.locator == "https://en.wikisource.org/wiki/Some_Page"


def test_wikisource_normalizes_foreign_host_to_en():
    c = canonicalize_wikisource("https://fr.wikisource.org/wiki/Republic")
    assert c.locator == "https://en.wikisource.org/wiki/Republic"


def test_gutenberg_empty_rejected():
    with pytest.raises(ValueError, match="empty"):
        canonicalize_gutenberg("  ")


def test_gutenberg_invalid_rejected():
    with pytest.raises(ValueError, match="Could not extract"):
        canonicalize_gutenberg("not-a-url-or-id")


def test_wikisource_non_wikisource_host():
    with pytest.raises(ValueError, match="wikisource"):
        canonicalize_wikisource("https://example.com/wiki/Foo")


def test_wikisource_missing_wiki_path():
    with pytest.raises(ValueError, match="/wiki/"):
        canonicalize_wikisource("https://en.wikisource.org/w/index.php?title=Foo")
