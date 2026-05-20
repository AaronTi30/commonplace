from __future__ import annotations

import os
import tempfile
import uuid

from sqlalchemy import text


def _seed_work(db_session, *, author: str = "Plato", title: str = "Republic", source_type: str = "gutenberg"):
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO sources (id, source_type, locator, canonical_url) VALUES (:id,:t,:l,:u)"
        ),
        {"id": source_id, "t": source_type, "l": str(uuid.uuid4()), "u": "https://example.com"},
    )
    db_session.execute(
        text(
            "INSERT INTO works (id, source_id, title, author, ingestion_state) VALUES (:id,:s,:title,:author,'complete')"
        ),
        {"id": work_id, "s": source_id, "title": title, "author": author},
    )
    return work_id, source_id


def test_list_works_filters(client, db_session):
    w1, _ = _seed_work(db_session, author="Plato", title="Republic", source_type="gutenberg")
    _seed_work(db_session, author="Aristotle", title="Metaphysics", source_type="wikisource")

    resp = client.get("/api/works?author=plat&source_type=gutenberg")
    assert resp.status_code == 200
    works = resp.json()["works"]
    assert len(works) == 1
    assert works[0]["work_id"] == str(w1)


def test_get_work_paginates_by_passage_index(client, db_session):
    work_id, _ = _seed_work(db_session)
    pids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    for i, pid in enumerate(pids, start=1):
        db_session.execute(
            text(
                "INSERT INTO passages (id, work_id, passage_index, cleaned_text, citation_string, chunker_version) "
                "VALUES (:id,:w,:i,:t,:c,'mvp-1')"
            ),
            {"id": pid, "w": work_id, "i": i, "t": f"p{i}", "c": f"c{i}"},
        )

    r1 = client.get(f"/api/works/{work_id}?limit=2")
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["passages"]) == 2
    assert body1["next_cursor"] == "2"

    r2 = client.get(f"/api/works/{work_id}?limit=2&cursor={body1['next_cursor']}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["passages"]) == 1
    assert "next_cursor" not in body2


def test_delete_work_removes_work_and_source(client, db_session):
    work_id, source_id = _seed_work(db_session, author="Jane Austen", title="Pride and Prejudice")
    passage_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO passages (id, work_id, passage_index, cleaned_text, citation_string, chunker_version) "
            "VALUES (:id,:w,1,'p','c','mvp-1')"
        ),
        {"id": passage_id, "w": work_id},
    )
    # Embeddings row references works via work_id RESTRICT, so delete must handle it.
    db_session.execute(
        text(
            "INSERT INTO passage_embeddings (id, passage_id, work_id, embedding_model, embedding_dim, embedding) "
            "VALUES (:id,:p,:w,'sentence-transformers/all-MiniLM-L6-v2',384, :vec)"
        ),
        {"id": uuid.uuid4(), "p": passage_id, "w": work_id, "vec": [0.0] * 384},
    )

    resp = client.delete(f"/api/works/{work_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Work is gone
    r2 = client.get(f"/api/works/{work_id}")
    assert r2.status_code == 404

    # Source is gone (and thus won't appear indirectly anywhere)
    src_count = db_session.execute(text("SELECT COUNT(*) FROM sources WHERE id = :s"), {"s": source_id}).scalar()
    assert src_count == 0


def test_delete_work_404(client, db_session):
    resp = client.delete(f"/api/works/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_patch_work_updates_fields(client, db_session):
    work_id, _ = _seed_work(db_session, author="A", title="B")
    resp = client.patch(f"/api/works/{work_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    w = resp.json()["work"]
    assert w["title"] == "New Title"
    assert w["author"] == "A"

    r2 = client.get(f"/api/works/{work_id}")
    assert r2.json()["work"]["title"] == "New Title"


def test_patch_work_404(client, db_session):
    resp = client.patch(f"/api/works/{uuid.uuid4()}", json={"title": "X"})
    assert resp.status_code == 404


def test_delete_epub_removes_upload_file(client, db_session, tmp_path):
    path = tmp_path / "book.epub"
    path.write_bytes(b"%PDF-epub-test-bytes")
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    art_id = uuid.uuid4()
    digest = "b" * 64
    db_session.execute(
        text(
            "INSERT INTO sources (id, source_type, locator, canonical_url) "
            "VALUES (:id,'epub',:loc,'file://book.epub')"
        ),
        {"id": source_id, "loc": digest},
    )
    db_session.execute(
        text(
            "INSERT INTO works (id, source_id, title, author, ingestion_state) "
            "VALUES (:id,:s,'T','A','complete')"
        ),
        {"id": work_id, "s": source_id},
    )
    db_session.execute(
        text(
            "INSERT INTO source_artifacts (id, source_id, raw_file_path, http_status, content_sha256) "
            "VALUES (:id,:s,:p,200,:sha)"
        ),
        {"id": art_id, "s": source_id, "p": str(path), "sha": digest},
    )
    db_session.flush()
    assert path.is_file()

    resp = client.delete(f"/api/works/{work_id}")
    assert resp.status_code == 200
    assert not path.is_file()


def test_delete_epub_succeeds_when_upload_file_already_missing(client, db_session, tmp_path):
    missing = tmp_path / "gone.epub"
    source_id = uuid.uuid4()
    work_id = uuid.uuid4()
    art_id = uuid.uuid4()
    digest = "c" * 64
    db_session.execute(
        text(
            "INSERT INTO sources (id, source_type, locator, canonical_url) "
            "VALUES (:id,'epub',:loc,'file://gone.epub')"
        ),
        {"id": source_id, "loc": digest},
    )
    db_session.execute(
        text(
            "INSERT INTO works (id, source_id, title, author, ingestion_state) "
            "VALUES (:id,:s,'T','A','complete')"
        ),
        {"id": work_id, "s": source_id},
    )
    db_session.execute(
        text(
            "INSERT INTO source_artifacts (id, source_id, raw_file_path, http_status, content_sha256) "
            "VALUES (:id,:s,:p,200,:sha)"
        ),
        {"id": art_id, "s": source_id, "p": str(missing), "sha": digest},
    )
    db_session.flush()
    assert not missing.exists()

    resp = client.delete(f"/api/works/{work_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def _seed_epub_work_with_file(db_session) -> tuple[uuid.UUID, str]:
    """Seed a complete epub work with a real file on disk. Returns (work_id, file_path)."""
    from app.db.models import IngestionState, Source, SourceArtifact, SourceType, Work

    tmp = tempfile.NamedTemporaryFile(suffix=".epub", delete=False)
    tmp.write(b"fake epub content")
    tmp.close()
    file_path = tmp.name

    source = Source(
        id=uuid.uuid4(),
        source_type=SourceType.epub,
        locator="abc123",
        canonical_url="file://test.epub",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        title="Test Book",
        author="Test Author",
        ingestion_state=IngestionState.complete,
    )
    artifact = SourceArtifact(
        id=uuid.uuid4(),
        source_id=source.id,
        http_status=200,
        raw_file_path=file_path,
    )
    db_session.add_all([source, work, artifact])
    return work.id, file_path


def test_get_work_file_returns_file_for_epub(client, db_session):
    work_id, file_path = _seed_epub_work_with_file(db_session)
    try:
        r = client.get(f"/api/works/{work_id}/file")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/epub+zip"
        assert r.content == b"fake epub content"
    finally:
        os.unlink(file_path)


def test_get_work_file_404_for_gutenberg(client, db_session):
    from app.db.models import IngestionState, Source, SourceArtifact, SourceType, Work

    source = Source(
        id=uuid.uuid4(),
        source_type=SourceType.gutenberg,
        locator="1342",
        canonical_url="https://gutenberg.org/1342",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        ingestion_state=IngestionState.complete,
    )
    artifact = SourceArtifact(
        id=uuid.uuid4(),
        source_id=source.id,
        http_status=200,
        raw_text="raw text here",
    )
    db_session.add_all([source, work, artifact])
    r = client.get(f"/api/works/{work.id}/file")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "file_not_available"


def test_get_work_file_404_when_file_missing_from_disk(client, db_session):
    work_id, file_path = _seed_epub_work_with_file(db_session)
    os.unlink(file_path)
    r = client.get(f"/api/works/{work_id}/file")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "file_not_found"


def _seed_minimal_work(db_session) -> uuid.UUID:
    from app.db.models import IngestionState, Source, SourceType, Work

    source = Source(
        id=uuid.uuid4(),
        source_type=SourceType.gutenberg,
        locator=str(uuid.uuid4()),
        canonical_url="https://example.com",
    )
    work = Work(
        id=uuid.uuid4(),
        source_id=source.id,
        ingestion_state=IngestionState.complete,
    )
    db_session.add_all([source, work])
    return work.id


def test_get_progress_returns_null_when_no_progress(client, db_session):
    work_id = _seed_minimal_work(db_session)
    r = client.get(f"/api/works/{work_id}/progress")
    assert r.status_code == 200
    assert r.json() == {"position": None}


def test_put_then_get_progress_round_trips(client, db_session):
    work_id = _seed_minimal_work(db_session)
    cfi = "epubcfi(/6/4[chap01]!/4/2/1:0)"

    r = client.put(f"/api/works/{work_id}/progress", json={"position": cfi})
    assert r.status_code == 200
    assert r.json() == {"position": cfi}

    r2 = client.get(f"/api/works/{work_id}/progress")
    assert r2.status_code == 200
    assert r2.json() == {"position": cfi}


def test_put_progress_twice_overwrites(client, db_session):
    work_id = _seed_minimal_work(db_session)

    client.put(f"/api/works/{work_id}/progress", json={"position": "epubcfi(/6/2)"})
    r = client.put(f"/api/works/{work_id}/progress", json={"position": "epubcfi(/6/8)"})
    assert r.status_code == 200

    r2 = client.get(f"/api/works/{work_id}/progress")
    assert r2.json()["position"] == "epubcfi(/6/8)"


def test_get_progress_404_for_missing_work(client, db_session):
    r = client.get(f"/api/works/{uuid.uuid4()}/progress")
    assert r.status_code == 404


def test_put_progress_404_for_missing_work(client, db_session):
    r = client.put(f"/api/works/{uuid.uuid4()}/progress", json={"position": "42"})
    assert r.status_code == 404
