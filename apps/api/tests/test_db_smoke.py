import uuid

from sqlalchemy import select, text

from app.db.models import ReadingProgress


def test_db_smoke(db_session):
    # sources
    source_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO sources (id, source_type, locator, canonical_url)
            VALUES (:id, 'gutenberg', '1342', 'https://www.gutenberg.org/ebooks/1342')
            """
        ),
        {"id": source_id},
    )

    # source_artifacts: exactly one of raw_text / raw_html / raw_file_path
    db_session.execute(
        text(
            """
            INSERT INTO source_artifacts (id, source_id, raw_text)
            VALUES (:id, :source_id, :raw_text)
            """
        ),
        {"id": uuid.uuid4(), "source_id": source_id, "raw_text": "Hello world"},
    )

    epub_source_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO sources (id, source_type, locator, canonical_url)
            VALUES (:id, 'epub', 'deadbeef', 'file://fixture.epub')
            """
        ),
        {"id": epub_source_id},
    )
    db_session.execute(
        text(
            """
            INSERT INTO source_artifacts (id, source_id, raw_file_path, http_status, content_sha256)
            VALUES (:id, :source_id, :path, 200, :sha)
            """
        ),
        {
            "id": uuid.uuid4(),
            "source_id": epub_source_id,
            "path": "/tmp/commonplace_fixture.epub",
            "sha": "a" * 64,
        },
    )

    # works
    work_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO works (id, source_id, title, author, language, ingestion_state)
            VALUES (:id, :source_id, 'Test Work', 'Tester', 'en', 'queued')
            """
        ),
        {"id": work_id, "source_id": source_id},
    )

    # passages
    passage_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO passages (id, work_id, passage_index, cleaned_text, citation_string, chunker_version)
            VALUES (:id, :work_id, 0, 'A passage', 'Tester — Test Work, §, ¶0', 'v1')
            """
        ),
        {"id": passage_id, "work_id": work_id},
    )

    # passage_embeddings: work_id is set by trigger based on passage_id
    emb_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO passage_embeddings (id, passage_id, work_id, embedding_model, embedding_dim, embedding)
            VALUES (:id, :passage_id, :work_id, 'sentence-transformers/all-MiniLM-L6-v2', 384, :embedding)
            """
        ),
        {
            "id": emb_id,
            "passage_id": passage_id,
            "work_id": uuid.uuid4(),  # should be overwritten by trigger
            "embedding": [0.0] * 384,
        },
    )

    row = db_session.execute(
        text("SELECT work_id FROM passage_embeddings WHERE id = :id"), {"id": emb_id}
    ).fetchone()
    assert row is not None
    assert row.work_id == work_id

    # ingestion_jobs
    job_id = uuid.uuid4()
    db_session.execute(
        text(
            """
            INSERT INTO ingestion_jobs (id, job_type, status, work_id, payload)
            VALUES (:id, 'ingest_work', 'queued', :work_id, '{}'::jsonb)
            """
        ),
        {"id": job_id, "work_id": work_id},
    )


def test_reading_progress_table_exists(db_session):
    """Confirm the reading_progress table is reachable."""
    result = db_session.execute(select(ReadingProgress)).all()
    assert result == []

