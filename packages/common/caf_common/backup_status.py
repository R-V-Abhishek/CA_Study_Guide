"""Status record written by scheduled snapshots; read by the host, API and alarms."""

import json
import os
from pathlib import Path

STATUS = "status.json"


def write_status(base: Path, status: dict) -> None:
    """Atomic and world-readable: it holds no secrets and the host script and API read it."""
    temporary = base / (STATUS + ".tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    temporary.chmod(0o644)
    os.replace(temporary, base / STATUS)


def read_status(base: Path) -> dict | None:
    path = base / STATUS
    return json.loads(path.read_text()) if path.is_file() else None
