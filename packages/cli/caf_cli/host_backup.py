"""Scheduled recovery snapshots. Runs inside the web image as the application user;
the host script adds optional encryption and never receives the Docker socket in Python."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import typer

from caf_common.backup import create_backup, critical_tables
from caf_common.backup_status import read_status, write_status
from caf_common.recovery_manifest import checksum, inspect_recovery_files
from caf_common.retention import SNAPSHOT_ID, plan_retention

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
def verified_snapshots(base: Path) -> list[str]:
    """Only real directories with a manifest take part in retention; anything else is left for review."""
    return sorted(entry.name for entry in base.iterdir()
                  if SNAPSHOT_ID.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink()
                  and (entry / "manifest.json").is_file())


def apply_retention(base: Path, *, daily: int, weekly: int, monthly: int) -> tuple[list[str], list[str]]:
    keep, delete = plan_retention(verified_snapshots(base), daily=daily, weekly=weekly, monthly=monthly)
    for identifier in delete:
        shutil.rmtree(base / identifier)
    return keep, delete


def run_backup(base: Path, *, daily: int = 7, weekly: int = 4, monthly: int = 6, session=None) -> dict:
    """Capture, verify, then prune. A failure never prunes and always leaves a status record."""
    started = datetime.now(timezone.utc)
    previous = read_status(base) or {}
    status = {"state": "failed", "last_attempt_at": started.isoformat(),
              "last_success_at": previous.get("last_success_at"), "snapshot": previous.get("snapshot"),
              "retained": previous.get("retained", []), "encryption": previous.get("encryption", "not_configured"),
              "error": None}
    try:
        manifest = create_backup(session=session, backup_dir=base)
        snapshot = manifest.backup_dir
        recovery = inspect_recovery_files(snapshot)
        if critical_tables(recovery.database_revision) - recovery.tables.keys():
            raise ValueError("Snapshot is missing protected tables")
        keep, deleted = apply_retention(base, daily=daily, weekly=weekly, monthly=monthly)
        status.update(state="ok", last_success_at=datetime.now(timezone.utc).isoformat(), retained=keep,
                      deleted=deleted, error=None, encryption="pending",
                      snapshot={"name": snapshot.name, "manifest_sha256": checksum(snapshot / "manifest.json"),
                                "created_at": recovery.created_at.isoformat(),
                                "database_revision": recovery.database_revision,
                                "dump_bytes": manifest.dump_size_bytes, "archived_files": len(recovery.files),
                                "file_integrity_verified": True, "restore_verified": False})
    except Exception as error:
        # Operators see the class and message in the private status file; nothing is swallowed.
        status["error"] = f"{type(error).__name__}: {error}"
        write_status(base, status)
        raise
    write_status(base, status)
    return status


@app.command("run")
def run_command(daily: int = 7, weekly: int = 4, monthly: int = 6) -> None:
    from caf_common.settings import get_settings
    from caf_db.engine import get_session_factory

    with get_session_factory("operations")() as session:
        status = run_backup(Path(get_settings().storage.backup_dir), daily=daily, weekly=weekly,
                            monthly=monthly, session=session)
    typer.echo(json.dumps({"state": status["state"], "snapshot": status["snapshot"]["name"],
                           "retained": len(status["retained"]), "deleted": status["deleted"]}))


@app.command("mark-encryption")
def mark_encryption(result: str = typer.Argument(..., help="encrypted | not_configured | failed:<reason>")) -> None:
    """Record the host script's encryption outcome next to the snapshot it belongs to."""
    from caf_common.settings import get_settings

    base = Path(get_settings().storage.backup_dir)
    status = read_status(base)
    if status is None:
        raise ValueError("No backup status to update")
    status["encryption"] = result
    if result.startswith("failed"):
        status["state"] = "failed"
        status["error"] = result
    write_status(base, status)
