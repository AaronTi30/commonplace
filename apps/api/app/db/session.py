from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings import settings


def create_app_engine():
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it in the environment "
            "(see apps/api/.env.example)."
        )
    return create_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

