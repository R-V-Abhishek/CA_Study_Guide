"""Backup, verification, and rotation engine for the CA Final study companion."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.settings import get_settings
from caf_db.models.ops import Event

logger = logging.getLogger(__name__)

# Tables whose row counts must match during verify drills
CRITICAL_TABLES = [
    "app.user_account",
    "app.settings",
    "app.progress",
    "app.progress_event",
    "app.revision_event",
    "app.mock_test",
    "core.decision",
    "core.appearance",
    "core.appearance_tag",
    "core.change_log",
]


@dataclass
class BackupManifest:
    dump_file: Path
    dump_size_bytes: int
    blobs_copied: int
    configs_copied: int
    created_at: datetime
    backup_dir: Path


@dataclass
class VerificationResult:
    verified: bool
    dump_file: Path
    live_counts: dict[str, int]
    restored_counts: dict[str, int]
    mismatches: list[str]
    message: str


def _parse_db_conn_params(db_url: str | None = None) -> dict[str, Any]:
    """Parse connection parameters from settings or URL string."""
    if not db_url:
        settings = get_settings()
        db_url = settings.DATABASE_URL or settings.database.url

    # Strip dialect prefix if any (e.g. postgresql+psycopg:// -> postgresql://)
    if "+" in db_url.split("://")[0]:
        dialect = db_url.split("://")[0].split("+")[0]
        rest = db_url.split("://", 1)[1]
        db_url = f"{dialect}://{rest}"

    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "database": (parsed.path.lstrip("/") if parsed.path else "caf"),
    }


def rotate_backups(
    backup_dir: Path | str,
    max_daily: int = 14,
    max_weekly: int = 8,
) -> list[Path]:
    """Retain up to max_daily daily backups and max_weekly weekly backups; prune older.
    
    Returns list of deleted dump file paths.
    """
    b_dir = Path(backup_dir)
    if not b_dir.exists():
        return []

    dump_files = sorted(
        [p for p in b_dir.glob("caf_*.dump") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not dump_files:
        return []

    # Map each dump to a calendar date YYYY-MM-DD and calendar week YYYY-WW
    daily_kept: dict[str, Path] = {}
    weekly_kept: dict[str, Path] = {}
    keep_set: set[Path] = set()

    for p in dump_files:
        dt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        week_key = dt.strftime("%Y-%W")

        # Keep latest dump for each day up to max_daily days
        if len(daily_kept) < max_daily and day_key not in daily_kept:
            daily_kept[day_key] = p
            keep_set.add(p)

        # Keep latest dump for each week up to max_weekly weeks
        if len(weekly_kept) < max_weekly and week_key not in weekly_kept:
            weekly_kept[week_key] = p
            keep_set.add(p)

    deleted = []
    for p in dump_files:
        if p not in keep_set:
            try:
                p.unlink()
                deleted.append(p)
                logger.info(f"Rotated stale backup: {p}")
            except Exception as e:
                logger.warning(f"Failed to delete stale backup {p}: {e}")

    return deleted


def create_backup(
    session: Session | None = None,
    backup_dir: Path | str | None = None,
    blob_dir: Path | str | None = None,
    target_dir: Path | str | None = None,
    db_url: str | None = None,
) -> BackupManifest:
    """Execute nightly backup: pg_dump, blob sync, config archive, and rotation.
    
    1. pg_dump -Fc -d caf -f data/backups/caf_<ts>.dump
    2. sync data/blobs/ to backup target
    3. Copy taxonomy/, config/, overrides/
    4. Rotate backups (keep 14 daily and 8 weekly)
    5. Write ops.event code=BACKUP_OK
    """
    settings = get_settings()
    b_dir = Path(backup_dir) if backup_dir else Path(settings.storage.backup_dir)
    b_dir.mkdir(parents=True, exist_ok=True)

    b_blobs = Path(blob_dir) if blob_dir else Path(settings.storage.blob_dir)

    now = datetime.now(timezone.utc)
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    dump_filename = f"caf_{ts_str}.dump"
    dump_path = b_dir / dump_filename

    # 1. Run pg_dump
    conn_params = _parse_db_conn_params(db_url)
    env = os.environ.copy()
    if conn_params["password"]:
        env["PGPASSWORD"] = conn_params["password"]

    pg_dump_cmd = [
        "pg_dump",
        "-h", conn_params["host"],
        "-p", conn_params["port"],
        "-U", conn_params["user"],
        "-Fc",
        "-d", conn_params["database"],
        "-f", str(dump_path),
    ]

    try:
        res = subprocess.run(
            pg_dump_cmd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        # Check /opt/homebrew/bin or /usr/local/bin
        alt_dump = "/opt/homebrew/bin/pg_dump" if Path("/opt/homebrew/bin/pg_dump").exists() else "/usr/local/bin/pg_dump"
        pg_dump_cmd[0] = alt_dump
        res = subprocess.run(
            pg_dump_cmd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    dump_size = dump_path.stat().st_size

    # 2. Sync blobs
    blobs_copied = 0
    blobs_backup_target = (Path(target_dir) / "blobs") if target_dir else (b_dir / "blobs")
    blobs_backup_target.mkdir(parents=True, exist_ok=True)
    if b_blobs.exists():
        for f in b_blobs.rglob("*"):
            if f.is_file():
                rel_path = f.relative_to(b_blobs)
                dest = blobs_backup_target / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                    shutil.copy2(f, dest)
                    blobs_copied += 1

    # 3. Copy config directories (taxonomy, config, overrides)
    configs_copied = 0
    configs_target = b_dir / "configs"
    configs_target.mkdir(parents=True, exist_ok=True)
    for cfg_folder_name in ["taxonomy", "config", "overrides", "profiles"]:
        src = Path(cfg_folder_name)
        if src.exists() and src.is_dir():
            dest = configs_target / cfg_folder_name
            shutil.copytree(src, dest, dirs_exist_ok=True)
            configs_copied += sum(1 for p in src.rglob("*") if p.is_file())

    # 4. Rotation: keep 14 daily, 8 weekly
    rotate_backups(b_dir, max_daily=14, max_weekly=8)

    manifest = BackupManifest(
        dump_file=dump_path,
        dump_size_bytes=dump_size,
        blobs_copied=blobs_copied,
        configs_copied=configs_copied,
        created_at=now,
        backup_dir=b_dir,
    )

    # 5. Record ops.event if session provided
    if session:
        try:
            event = Event(
                level="info",
                code="BACKUP_OK",
                message=f"Backup completed: {dump_filename} ({dump_size} bytes)",
                context={
                    "dump_file": str(dump_path),
                    "dump_size_bytes": dump_size,
                    "blobs_copied": blobs_copied,
                    "configs_copied": configs_copied,
                    "created_at": now.isoformat(),
                },
            )
            session.add(event)
            session.commit()
        except Exception as e:
            logger.warning(f"Could not record ops.event for backup: {e}")

    logger.info(f"Backup created: {dump_path} ({dump_size} bytes)")
    return manifest


def verify_backup(
    session: Session,
    dump_file: Path | str | None = None,
    scratch_db_name: str = "caf_verify",
    db_url: str | None = None,
) -> VerificationResult:
    """Verify backup by restoring into a scratch database and checking critical table row counts."""
    settings = get_settings()
    b_dir = Path(settings.storage.backup_dir)

    if dump_file is None:
        dumps = sorted(
            [p for p in b_dir.glob("caf_*.dump") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not dumps:
            raise FileNotFoundError(f"No backup dumps found in {b_dir} to verify")
        dump_path = dumps[0]
    else:
        dump_path = Path(dump_file)
        if not dump_path.exists():
            raise FileNotFoundError(f"Backup dump not found: {dump_path}")

    # 1. Fetch live row counts for critical tables
    live_counts: dict[str, int] = {}
    for table_name in CRITICAL_TABLES:
        try:
            cnt = session.execute(sa.text(f"SELECT COUNT(*) FROM {table_name};")).scalar() or 0
            live_counts[table_name] = cnt
        except Exception:
            live_counts[table_name] = 0

    # 2. Connect to postgres admin and prepare scratch database
    conn_params = _parse_db_conn_params(db_url)
    env = os.environ.copy()
    if conn_params["password"]:
        env["PGPASSWORD"] = conn_params["password"]

    admin_url = (
        f"postgresql+psycopg://{conn_params['user']}:{conn_params['password']}@"
        f"{conn_params['host']}:{conn_params['port']}/postgres"
    )
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")

    restored_counts: dict[str, int] = {}
    mismatches: list[str] = []
    verified = False
    message = ""

    try:
        with admin_engine.connect() as admin_conn:
            # Drop scratch if exists
            admin_conn.execute(sa.text(f"DROP DATABASE IF EXISTS {scratch_db_name} WITH (FORCE);"))
            # Create scratch
            admin_conn.execute(sa.text(f"CREATE DATABASE {scratch_db_name};"))

        # 3. Restore dump into scratch DB using pg_restore
        pg_restore_bin = "pg_restore"
        if not shutil.which(pg_restore_bin):
            alt_res = "/opt/homebrew/bin/pg_restore" if Path("/opt/homebrew/bin/pg_restore").exists() else "/usr/local/bin/pg_restore"
            if Path(alt_res).exists():
                pg_restore_bin = alt_res

        restore_cmd = [
            pg_restore_bin,
            "-h", conn_params["host"],
            "-p", conn_params["port"],
            "-U", conn_params["user"],
            "-d", scratch_db_name,
            "-Fc",
            "--no-owner",
            str(dump_path),
        ]

        # pg_restore may return 1 if minor warnings occurred during restore
        subprocess.run(
            restore_cmd,
            env=env,
            capture_output=True,
            check=False,
        )

        # 4. Connect to scratch DB and count rows
        scratch_url = (
            f"postgresql+psycopg://{conn_params['user']}:{conn_params['password']}@"
            f"{conn_params['host']}:{conn_params['port']}/{scratch_db_name}"
        )
        scratch_engine = sa.create_engine(scratch_url)

        with scratch_engine.connect() as scratch_conn:
            for table_name in CRITICAL_TABLES:
                try:
                    cnt = scratch_conn.execute(sa.text(f"SELECT COUNT(*) FROM {table_name};")).scalar() or 0
                    restored_counts[table_name] = cnt
                except Exception:
                    restored_counts[table_name] = 0

                if live_counts[table_name] != restored_counts[table_name]:
                    mismatches.append(
                        f"{table_name}: live={live_counts[table_name]} vs restored={restored_counts[table_name]}"
                    )

        scratch_engine.dispose()

        if not mismatches:
            verified = True
            message = f"Backup verification succeeded: all {len(CRITICAL_TABLES)} critical tables match."
        else:
            verified = False
            message = f"Backup verification mismatch: {len(mismatches)} table(s) differ: {', '.join(mismatches)}"

    finally:
        # 5. Clean up scratch DB
        try:
            with admin_engine.connect() as admin_conn:
                admin_conn.execute(sa.text(f"DROP DATABASE IF EXISTS {scratch_db_name} WITH (FORCE);"))
            admin_engine.dispose()
        except Exception as e:
            logger.warning(f"Could not drop scratch DB {scratch_db_name}: {e}")

    # 6. Record ops.event
    try:
        event = Event(
            level="info" if verified else "alarm",
            code="BACKUP_VERIFIED_OK" if verified else "BACKUP_VERIFIED_FAILED",
            message=message,
            context={
                "dump_file": str(dump_path),
                "verified": verified,
                "mismatches": mismatches,
                "live_counts": live_counts,
                "restored_counts": restored_counts,
            },
        )
        session.add(event)
        session.commit()
    except Exception as e:
        logger.warning(f"Could not record verification event: {e}")

    return VerificationResult(
        verified=verified,
        dump_file=dump_path,
        live_counts=live_counts,
        restored_counts=restored_counts,
        mismatches=mismatches,
        message=message,
    )


def list_backups(backup_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """List existing backup dumps with size and timestamp."""
    settings = get_settings()
    b_dir = Path(backup_dir) if backup_dir else Path(settings.storage.backup_dir)
    if not b_dir.exists():
        return []

    dump_files = sorted(
        [p for p in b_dir.glob("caf_*.dump") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    now = datetime.now(timezone.utc)
    results = []
    for p in dump_files:
        stat = p.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age_hours = round((now - mtime).total_seconds() / 3600.0, 1)
        results.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created_at": mtime,
            "age_hours": age_hours,
        })
    return results
