"""Database engine and session management."""

from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from caf_common.settings import get_settings


def get_engine():
    settings = get_settings()
    url = settings.DATABASE_URL or settings.database.url
    return create_engine(url, pool_pre_ping=True)


_SessionLocal: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    with factory() as session:
        yield session
