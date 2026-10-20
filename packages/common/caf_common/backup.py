"""Snapshot-consistent recovery artifacts and independent PostgreSQL restore drills."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from caf_common.db_safety import assert_safe_database, assert_safe_storage
from caf_common.postgres_sandbox import PostgresSandbox
from caf_common.recovery_manifest import inspect_recovery_files
from caf_common.settings import get_settings
from caf_db.models.ops import Event
from caf_db.schema_baseline import schema_snapshot, compare_schema_snapshots, migrated_schema_snapshot

CRITICAL_TABLES = [
    "app.user_account", "app.settings", "app.progress", "app.progress_event",
    "app.note", "app.study_session", "app.revision_event", "app.mock_test",
    "core.decision", "core.appearance", "core.appearance_tag", "core.change_log",
]
SCHEMAS = ["app", "core", "ref", "ingest", "intel", "ops"]


def critical_tables(revision: str) -> set[str]:
    tables = set(CRITICAL_TABLES)
    if revision not in {"0001_initial_schema", "0002_score_config_snapshot"}:
        tables.update({"app.invitation", "app.login_transaction", "app.auth_session"})
    if revision not in {"0001_initial_schema", "0002_score_config_snapshot", "0003_identity"}:
        tables.update({"ref.taxonomy_release", "ref.taxonomy_member", "ref.textbook_artifact",
                       "ref.node_source_span", "ref.descriptor_revision", "ref.descriptor_approval",
                       "ref.taxonomy_crosswalk", "app.progress_migration"})
    if revision not in {"0001_initial_schema", "0002_score_config_snapshot", "0003_identity", "0004_textbook_taxonomy"}:
        tables.update({"ingest.extraction_revision", "ingest.content_block", "ingest.extraction_asset",
                       "ingest.document_pair", "ingest.extraction_review", "ingest.reconciliation_link"})
    if revision not in {"0001_initial_schema", "0002_score_config_snapshot", "0003_identity",
                        "0004_textbook_taxonomy", "0005_extraction_revisions"}:
        tables.update({"ingest.suggestion_revision", "core.classification_revision",
                       "core.classification_event", "core.classification_verification",
                       "core.classification_dispute", "core.question_publication"})
    if revision in {"0007_question_reader", "0008_baseline_adoption", "0009_question_language"}:
        tables.update({"core.published_question", "core.published_source", "core.question_occurrence",
                       "core.corpus_generation", "intel.attempt_taxonomy_binding",
                       "intel.corpus_coverage", "intel.reviewed_prior", "intel.recompute_job",
                       "intel.score_run", "intel.subtopic_score"})
    if revision in {"0008_baseline_adoption", "0009_question_language"}:
        tables.update({'ref.candidate_catalog','core.baseline_adoption'})
    return tables


@dataclass
class BackupManifest:
    dump_file: Path
    dump_size_bytes: int
    blobs_copied: int
    configs_copied: int
    created_at: datetime
    backup_dir: Path
    manifest_file: Path


@dataclass
class VerificationResult:
    verified: bool
    dump_file: Path
    live_counts: dict[str, int]  # Compatibility name: captured manifest counts.
    restored_counts: dict[str, int]
    mismatches: list[str]
    message: str
    report_file: Path


def _database_url(db_url=None):
    from caf_db.engine import database_url
    url = make_url(db_url) if db_url else database_url("backup")
    assert_safe_database(url)
    return url


def _parse_db_conn_params(db_url=None) -> dict[str, Any]:
    url = _database_url(db_url)
    return {"host": url.host, "port": str(url.port or 5432), "user": url.username,
            "password": url.password or "", "database": url.database}


def _pg_command(binary, url, arguments):
    assert_safe_database(url)
    # Do not inherit libpq services or alternate destinations from the shell.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env["PGPASSWORD"] = url.password or ""
    command = [binary, "-h", url.host, "-p", str(url.port or 5432),
               "-U", url.username, "-d", url.database, *arguments]
    try:
        return subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{binary} failed ({exc.returncode}): {exc.stderr.strip()}") from exc


def file_checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def database_content(connection, schemas=SCHEMAS) -> dict[str, dict[str, Any]]:
    """Canonical PostgreSQL JSON rows in UTC, C-sorted, including duplicates."""
    # timestamptz JSON follows session TimeZone. Normalize presentation before
    # hashing so an Asia/Kolkata source and UTC restore describe identical bytes.
    connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
    tables = connection.execute(sa.text("""
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname = ANY(:schemas) ORDER BY schemaname, tablename
    """), {"schemas": list(schemas)}).all()
    result = {}
    quote = connection.dialect.identifier_preparer.quote
    for schema, name in tables:
        digest = hashlib.sha256()
        count = 0
        rows = connection.execute(sa.text(
            f'SELECT to_jsonb(t)::text FROM {quote(schema)}.{quote(name)} t '
            'ORDER BY to_jsonb(t)::text COLLATE "C"'
        ))
        for row in rows:
            digest.update(row[0].encode("utf-8") + b"\n")
            count += 1
        result[f"{schema}.{name}"] = {"count": count, "sha256": digest.hexdigest()}
    return result


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")


def _archive_tree(source: Path, destination: Path, root: Path) -> dict[str, str]:
    files = {}
    if not source.is_dir():
        raise FileNotFoundError(f"Required archive directory missing: {source}")
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Archive symlink requires explicit resolution: {path}")
        if not path.is_file():
            continue
        if path.name.startswith(".env") or path.suffix in {".key", ".pem"}:
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in {".toml", ".yaml", ".yml", ".json"}:
            content = re.sub(
                r'(?im)^(\s*[\w-]*(?:password|secret|api_key|token)[\w-]*\s*[=:]\s*).+$',
                r'\1"[REDACTED]"', path.read_text(),
            )
            target.write_text(content)
        else:
            shutil.copy2(path, target)
        files[target.relative_to(root).as_posix()] = file_checksum(target)
    return files


def _record_event(session, code, message, context, verified=True):
    if session is not None:
        session.add(Event(level="info" if verified else "alarm", code=code,
                          message=message, context=context))
        session.commit()


def create_backup(session: Session | None = None, backup_dir=None, blob_dir=None,
                  target_dir=None, db_url=None) -> BackupManifest:
    """Capture dump and manifest from one exported read-only snapshot; never rotate.

    Optional secondary copies contain the entire unique recovery artifact.
    """
    settings = get_settings()
    url = _database_url(db_url)
    base = Path(backup_dir or settings.storage.backup_dir)
    assert_safe_storage(base)
    assert_safe_storage(Path(blob_dir or settings.storage.blob_dir))
    if target_dir:
        assert_safe_storage(Path(target_dir))
    base.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    identifier = f"caf_{now:%Y%m%d_%H%M%S_%f}_{uuid4().hex[:8]}"
    root = base / identifier
    root.mkdir()
    dump_path = root / f"{identifier}.dump"
    manifest_path = root / "manifest.json"
    engine = sa.create_engine(url, isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            snapshot = connection.execute(sa.text("SELECT pg_export_snapshot()")).scalar_one()
            revision = connection.execute(sa.text("SELECT version_num FROM ops.alembic_version")).scalar_one()
            tables = database_content(connection)
            missing = sorted(critical_tables(revision) - tables.keys())
            if missing:
                raise RuntimeError(f"Protected tables missing: {missing}")
            schema = schema_snapshot(connection)
            _pg_command("pg_dump", url, ["--format=custom", f"--snapshot={snapshot}",
                                         "--file", str(dump_path)])
    finally:
        engine.dispose()
    files = _archive_tree(Path(blob_dir or settings.storage.blob_dir), root / "blobs", root)
    blobs_copied = len(files)
    for directory in ("taxonomy", "config", "profiles", "overrides"):
        files.update(_archive_tree(Path(directory), root / "configs" / directory, root))
    data = {"format_version": 1, "created_at": now.isoformat(), "database_revision": revision,
            "dump_file": dump_path.name, "dump_sha256": file_checksum(dump_path),
            "tables": tables, "schema": schema, "files": files,
            "digest_format": "PostgreSQL16 to_jsonb text, UTC timezone, C-sort, UTF-8 newline per row",
            "secrets": "Credential keys redacted; .env, .key and .pem files excluded"}
    _write_json(manifest_path, data)
    if target_dir:
        shutil.copytree(root, Path(target_dir) / identifier)
    manifest = BackupManifest(dump_path, dump_path.stat().st_size, blobs_copied,
                              len(files) - blobs_copied, now, root, manifest_path)
    _record_event(session, "BACKUP_OK", f"Backup completed: {dump_path.name}",
                  {"dump_file": str(dump_path), "manifest_file": str(manifest_path)})
    return manifest


def _check_scratch_destination(url, name):
    if not re.fullmatch(r"caf_verify(?:_[a-zA-Z0-9_]+)?", name):
        raise ValueError("Unsafe scratch destination: use caf_verify or caf_verify_<suffix>")
    if name in {url.database, "postgres", "template0", "template1"}:
        raise ValueError("Scratch destination cannot be an application/system database")
    admin_url = url.set(database="postgres")
    assert_safe_database(admin_url)
    admin = sa.create_engine(admin_url)
    try:
        with admin.connect() as conn:
            if conn.execute(sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                            {"name": name}).scalar():
                raise ValueError("Existing scratch database preserved; choose a new destination")
    finally:
        admin.dispose()


def compare_restored_database(url, manifest) -> tuple[dict[str, int], dict]:
    """Compare every restored table digest and the schema to the captured manifest."""
    assert_safe_database(url)
    engine = sa.create_engine(url, isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            restored = database_content(connection)
            restored_counts = {table: values["count"] for table, values in restored.items()}
            if restored.keys() != manifest["tables"].keys():
                raise ValueError("Restored table inventory mismatch (missing or unexpected tables)")
            mismatches = [table for table in restored if restored[table] != manifest["tables"][table]]
            if mismatches:
                raise ValueError(f"Restored content mismatch: {', '.join(mismatches)}")
            revision = connection.execute(sa.text("SELECT version_num FROM ops.alembic_version")).scalar_one()
            if revision != manifest["database_revision"]:
                raise ValueError("Database revision mismatch")
            restored_schema = schema_snapshot(connection)
            if compare_schema_snapshots(manifest["schema"], restored_schema):
                raise ValueError("Restored schema differs from manifest")
    finally:
        engine.dispose()
    return restored_counts, restored_schema


def verify_backup(session: Session | None = None, dump_file=None, scratch_db_name="caf_verify",
                  db_url=None) -> VerificationResult:
    """Restore in a separate disposable container and compare to captured values."""
    url = _database_url(db_url)
    _check_scratch_destination(url, scratch_db_name)
    if dump_file is None:
        backups = list_backups()
        if not backups:
            raise FileNotFoundError("No backup dumps found")
        dump_file = backups[0]["path"]
    dump_path = Path(dump_file)
    assert_safe_storage(dump_path)
    if not dump_path.is_file():
        raise FileNotFoundError(f"Backup dump not found: {dump_path}")
    root = dump_path.parent
    report_path = root / f"verification_{uuid4().hex}.json"
    expected_counts = {}
    restored_counts = {}
    mismatches = []
    restored_schema = None
    baseline_drift = None
    try:
        manifest = inspect_recovery_files(root).model_dump(by_alias=True)
        if manifest["dump_file"] != dump_path.name:
            raise ValueError("Invalid backup manifest")
        expected_counts = {table: values["count"] for table, values in manifest["tables"].items()}
        if critical_tables(manifest["database_revision"]) - expected_counts.keys():
            raise ValueError("Manifest missing protected tables")
        with PostgresSandbox("restore", use_tmpfs=False) as sandbox:
            sandbox.allow(scratch_db_name)
            baseline_name = f"{scratch_db_name}_baseline"
            sandbox.allow(baseline_name)
            admin = sa.create_engine(sandbox.url(), isolation_level="AUTOCOMMIT")
            try:
                with admin.connect() as connection:
                    connection.execute(sa.text(f'CREATE DATABASE "{scratch_db_name}"'))
                    connection.execute(sa.text(f'CREATE DATABASE "{baseline_name}"'))
            finally:
                admin.dispose()
            restored_url = sandbox.url(scratch_db_name)
            _pg_command("pg_restore", restored_url, ["--exit-on-error", "--no-owner", "--no-acl",
                                                      str(dump_path)])
            restored_counts, restored_schema = compare_restored_database(restored_url, manifest)
            baseline_engine = sa.create_engine(sandbox.url(baseline_name))
            try:
                with baseline_engine.connect() as connection:
                    baseline_schema = migrated_schema_snapshot(connection, manifest["database_revision"])
                    baseline_drift = compare_schema_snapshots(baseline_schema, restored_schema)
                    if baseline_drift:
                        raise ValueError("Restored schema differs from frozen migration baseline; resolve drift before later migrations")
            finally:
                baseline_engine.dispose()
        verified = True
        message = f"Backup verification succeeded: critical tables match; all {len(restored_counts)} table digests and archived files match the manifest."
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError, sa.exc.SQLAlchemyError) as exc:
        verified = False
        message = f"Backup verification failed: {exc}"
        if not mismatches:
            mismatches = [str(exc)]
    result = VerificationResult(verified, dump_path, expected_counts, restored_counts,
                                mismatches, message, report_path)
    report = asdict(result)
    report["expected_counts"] = report.pop("live_counts")
    report["restored_schema"] = restored_schema
    report["baseline_schema_drift"] = baseline_drift
    report["verified_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(report_path, report)
    _record_event(session, "BACKUP_VERIFIED_OK" if verified else "BACKUP_VERIFIED_FAILED",
                  message, {"verified": verified, "report_file": str(report_path)}, verified)
    return result


def list_backups(backup_dir=None) -> list[dict[str, Any]]:
    """List unique artifacts and identifiable legacy flat dumps."""
    base = Path(backup_dir or get_settings().storage.backup_dir)
    paths = [*base.glob("caf_*.dump"), *base.glob("caf_*/caf_*.dump")]
    now = datetime.now(timezone.utc)
    result = []
    for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        created = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        result.append({"name": path.name, "path": str(path), "size_bytes": stat.st_size,
                       "size_mb": round(stat.st_size / 1024**2, 2), "created_at": created,
                       "age_hours": round((now - created).total_seconds() / 3600, 1),
                       "legacy": not (path.parent / "manifest.json").is_file()})
    return result


def rotate_backups(backup_dir, max_daily=14, max_weekly=8) -> list[Path]:
    """Explicit legacy flat-dump retention; never invoked by checkpoint creation."""
    assert_safe_storage(Path(backup_dir))
    paths = sorted(Path(backup_dir).glob("caf_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    days, weeks, deleted = set(), set(), []
    for path in paths:
        at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        day, week = at.strftime("%Y-%m-%d"), at.strftime("%Y-%W")
        keep_day = len(days) < max_daily and day not in days
        keep_week = len(weeks) < max_weekly and week not in weeks
        if keep_day:
            days.add(day)
        if keep_week:
            weeks.add(week)
        if not (keep_day or keep_week):
            path.unlink()
            deleted.append(path)
    return deleted
