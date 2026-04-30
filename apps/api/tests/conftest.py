from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.main import app


def _require_test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required to run tests. "
            "It must point to an isolated database whose name ends with `_test` "
            "(see apps/api/.env.example)."
        )
    db_name = make_url(url).database
    if not db_name or not db_name.endswith("_test"):
        raise RuntimeError(
            f"TEST_DATABASE_URL database name must end with `_test`, got {db_name!r}."
        )
    return url


TEST_DATABASE_URL = _require_test_db_url()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    # Ensure schema is up-to-date via Alembic migrations.
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev

    yield engine

    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    with Session(db_engine) as session:
        session.execute(text("SET timezone TO 'UTC'"))
        yield session
        session.rollback()

