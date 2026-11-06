"""Alert evaluation for the host watcher. State lives beside the backup status; the host script only delivers."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import typer

from caf_common.backup_status import read_status
from caf_common.heartbeat import STALE_AFTER_SECONDS, read_heartbeat

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
STATE = "watch-state.json"
REMINDER = timedelta(hours=24)
BACKUP_MAX_AGE = timedelta(hours=48)


def find_problems(
    *, ready: bool, backup: dict | None, heartbeat: datetime | None, now: datetime
) -> dict[str, str]:
    problems = {}
    if not ready:
        problems["NOT_READY"] = "The application is not answering its readiness check"
    if heartbeat is None or (now - heartbeat).total_seconds() > STALE_AFTER_SECONDS:
        problems["WORKER_STALE"] = "The intelligence worker has not reported recently"
    if backup is not None and backup.get("state") == "failed":
        problems["BACKUP_FAILED"] = f"The latest recovery snapshot failed: {backup.get('error')}"
    elif (
        backup is None
        or not backup.get("last_success_at")
        or now - datetime.fromisoformat(backup["last_success_at"]) > BACKUP_MAX_AGE
    ):
        problems["BACKUP_STALE"] = "No recovery snapshot has succeeded in the last 48 hours"
    return problems


def decide(problems: dict[str, str], state: dict, now: datetime) -> tuple[list[dict], dict]:
    """One notification when a problem appears, one when it clears, one reminder per day while it lasts."""
    active = state.get("active", {})
    notifications, updated = [], {}
    for code, message in problems.items():
        previous = active.get(code)
        if previous is None:
            notifications.append({"kind": "alert", "code": code, "message": message})
            updated[code] = {"since": now.isoformat(), "notified_at": now.isoformat()}
        elif now - datetime.fromisoformat(previous["notified_at"]) >= REMINDER:
            notifications.append({"kind": "reminder", "code": code, "message": message})
            updated[code] = {**previous, "notified_at": now.isoformat()}
        else:
            updated[code] = previous
    for code in active.keys() - problems.keys():
        # BACKUP_FAILED and BACKUP_STALE describe one snapshot; a change between them is not a recovery.
        if code.startswith("BACKUP_") and any(other.startswith("BACKUP_") for other in problems):
            continue
        notifications.append({"kind": "recovered", "code": code, "message": "Back to normal"})
    return notifications, {"active": updated}


def check(base: Path, *, ready: bool, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    path = base / STATE
    state = json.loads(path.read_text()) if path.is_file() else {}
    problems = find_problems(
        ready=ready, backup=read_status(base), heartbeat=read_heartbeat(base), now=now
    )
    notifications, new_state = decide(problems, state, now)
    temporary = base / (STATE + ".tmp")
    temporary.write_text(json.dumps(new_state, indent=2) + "\n")
    temporary.replace(path)
    return notifications


@app.command("check")
def check_command(ready: bool = typer.Option(..., "--ready/--not-ready")) -> None:
    from caf_common.settings import get_settings

    typer.echo(json.dumps(check(Path(get_settings().storage.backup_dir), ready=ready)))
