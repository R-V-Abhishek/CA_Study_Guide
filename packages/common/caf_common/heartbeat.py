"""Worker liveness record; a file beside the backup status, so monitoring needs no database access."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

HEARTBEAT = "worker-heartbeat.json"
STALE_AFTER_SECONDS = 600


def write_heartbeat(base: Path, now: datetime | None = None) -> None:
    moment = (now or datetime.now(timezone.utc)).isoformat()
    temporary = base / (HEARTBEAT + ".tmp")
    temporary.write_text(json.dumps({"worker": "intelligence", "at": moment}) + "\n")
    temporary.chmod(0o644)
    os.replace(temporary, base / HEARTBEAT)


def read_heartbeat(base: Path) -> datetime | None:
    path = base / HEARTBEAT
    return datetime.fromisoformat(json.loads(path.read_text())["at"]) if path.is_file() else None
