"""Minimal readiness probe; detailed operational diagnostics stay authenticated."""

from functools import lru_cache
import logging
import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from caf_common.settings import get_settings
from caf_db.engine import get_engine

router = APIRouter()


@lru_cache(maxsize=1)
def required_schema() -> str:
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


@router.get("/api/v1/ready")
def ready() -> dict[str, str]:
    try:
        with get_engine("backup").connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM ops.alembic_version")).scalar_one()
        if revision != required_schema():
            raise ValueError("Schema differs from application migration head")
        storage = get_settings().storage
        for path in (storage.data_dir, storage.blob_dir):
            if path.is_symlink() or not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
                raise OSError("Required storage unavailable")
    except (SQLAlchemyError, OSError, ValueError, RuntimeError):
        logging.getLogger(__name__).warning("readiness_failed", extra={"code": "READINESS_FAILED"})
        raise HTTPException(503, "Service not ready") from None
    return {"status": "ready"}
