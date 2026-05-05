from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app.db.session import create_app_engine, create_session_factory


@lru_cache(maxsize=1)
def _session_factory():
    engine = create_app_engine()
    return create_session_factory(engine)


def get_db_session():
    SessionLocal = _session_factory()
    with SessionLocal() as session:
        yield session

