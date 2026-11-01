"""Database session dependencies shared by the API routers."""

from fastapi import Request

from caf_api.auth import get_identity_db  # noqa: F401  (re-exported for routers)
from caf_db.engine import get_session_factory


def get_db(request: Request):
    factory = get_session_factory("student")
    with factory() as session:
        # Repeated intelligence helpers share a snapshot only within this GET.
        # Mutations and pipeline sessions always resolve fresh context.
        session.info["cache_study_context"] = request.method in {"GET", "HEAD"}
        yield session


def get_operations_db():
    with get_session_factory("operations")() as session:
        yield session
