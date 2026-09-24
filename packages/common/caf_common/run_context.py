"""Pipeline run tracking context for ops.run."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
from typing import Any, Generator
from sqlalchemy import text
from caf_common.logging import get_logger
from caf_db.engine import get_session_factory
from caf_db.models.ops import Run

logger = get_logger("run_context")


def get_git_sha() -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        return res.stdout.strip()
    except Exception:
        return None


def get_config_hash(config_dir: Path = Path("config")) -> str:
    hasher = hashlib.sha256()
    if config_dir.exists():
        for file in sorted(config_dir.glob("*.toml")):
            hasher.update(file.name.encode())
            hasher.update(file.read_bytes())
    return hasher.hexdigest()[:16]


@contextmanager
def open_run(stage: str, args: dict[str, Any] | None = None) -> Generator[Run, None, None]:
    """Context manager that wraps execution in an ops.run lifecycle record."""
    session_factory = get_session_factory()
    session = session_factory()
    git_sha = get_git_sha()
    config_hash = get_config_hash()

    run = Run(
        stage=stage,
        git_sha=git_sha,
        config_hash=config_hash,
        args=args or {},
        status="running",
        stats={},
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    logger.info("run_started", stage=stage, run_id=run.id)
    try:
        yield run
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("run_finished", stage=stage, run_id=run.id, status=run.status)
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.error("run_failed", stage=stage, run_id=run.id, error=str(exc))
        raise
    finally:
        session.close()
