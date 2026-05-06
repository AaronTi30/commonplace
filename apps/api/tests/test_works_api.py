from __future__ import annotations

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
