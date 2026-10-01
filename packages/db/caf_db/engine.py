"""Database engine and session management."""

from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from caf_common.settings import get_settings
from caf_common.db_safety import assert_safe_database

_engines = []


def get_engine():
    settings = get_settings()
    url = settings.DATABASE_URL or settings.database.url
    assert_safe_database(url)
    engine = create_engine(url, pool_pre_ping=True)
    _engines.append(engine)
    return engine


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


def reset_database() -> None:
    """Dispose engines and cached sessions before changing a database target."""
    global _SessionLocal
    _SessionLocal = None
    for engine in _engines:
        engine.dispose()
    _engines.clear()
