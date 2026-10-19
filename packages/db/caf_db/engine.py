"""Named database pools: serving credentials never fall back to administration."""

from collections.abc import Generator
from typing import Literal

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from caf_common.settings import get_settings
from caf_common.db_safety import assert_safe_database

Operation = Literal["student", "identity", "curation", "operations", "pipeline", "backup", "migration"]
ROLE_NAMES = {
    "student": "caf_app", "identity": "caf_identity", "curation": "caf_curator",
    "operations": "caf_operations", "pipeline": "caf_pipeline", "backup": "caf_backup",
}
_engines: dict[str, Engine] = {}
_factories: dict[str, sessionmaker[Session]] = {}


def database_url(operation: Operation = "migration"):
    settings = get_settings()
    if operation == "migration":
        value = settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL or settings.database.url
    else:
        if operation not in ROLE_NAMES:
            raise ValueError(f"Unknown database operation: {operation}")
        value = settings.model_dump()[f"{operation.upper()}_DATABASE_URL"]
        if not value:
            raise RuntimeError(f"{operation.upper()}_DATABASE_URL is required; administrative fallback is forbidden")
    url = make_url(value)
    assert_safe_database(url)
    if operation != "migration" and url.username != ROLE_NAMES[operation]:
        raise RuntimeError(f"{operation} connections must authenticate as {ROLE_NAMES[operation]}")
    return url


def get_engine(operation: Operation = "migration") -> Engine:
    if operation not in _engines:
        engine = create_engine(database_url(operation), pool_pre_ping=True)
        if operation != "migration":
            @event.listens_for(engine, "connect")
            def check_role(connection, record):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname=current_user")
                    if any(cursor.fetchone()):
                        raise RuntimeError("Serving database role has administrative privileges")
                connection.rollback()
        _engines[operation] = engine
    return _engines[operation]


def get_session_factory(operation: Operation = "migration") -> sessionmaker[Session]:
    if operation not in _factories:
        _factories[operation] = sessionmaker(bind=get_engine(operation), expire_on_commit=False)
    return _factories[operation]


def get_db_session() -> Generator[Session, None, None]:
    with get_session_factory("student")() as session:
        yield session


def reset_database() -> None:
    _factories.clear()
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
