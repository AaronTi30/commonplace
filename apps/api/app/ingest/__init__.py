"""Ingestion pipeline: canonicalization, fetchers, normalize, chunk, embed."""

from app.ingest.canonicalize import (
    CanonicalGutenberg,
    CanonicalWikisource,
    canonicalize_gutenberg,
    canonicalize_wikisource,
)

__all__ = [
    "CanonicalGutenberg",
    "CanonicalWikisource",
    "canonicalize_gutenberg",
    "canonicalize_wikisource",
]
