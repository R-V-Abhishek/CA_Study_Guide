"""Restore a Phase 4 checkpoint before applying the classification migration."""

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
import typer

from caf_common.backup import (
    _pg_command, _validate_archived_files, database_content, file_checksum,
)
from caf_common.postgres_sandbox import PostgresSandbox
from caf_db.engine import get_engine
from caf_db.grants import apply_grants
from caf_db.schema_baseline import schema_snapshot, compare_schema_snapshots
from phase3_prepare import original_snapshot, preserved_content

app = typer.Typer(pretty_exceptions_show_locals=False)
HEAD = "0006_classification_revisions"
MIGRATION = Path(f"packages/db/caf_db/alembic/versions/{HEAD}.py")


def migrate(connection):
    before = original_snapshot(connection)
    revision = connection.scalar(sa.text("SELECT version_num FROM ops.alembic_version"))
    if revision not in {"0005_extraction_revisions", HEAD}:
        raise ValueError(f"Expected the Phase 4 schema; found {revision}")
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, HEAD)
    preserved = preserved_content(connection, before)
    expected = {name: value for name, value in before["tables"].items()
                if name != "ops.alembic_version"}
    if preserved != expected:
        raise ValueError("Migration changed original values; transaction aborted")
    return {"from_revision": revision, "to_revision": HEAD,
            "migration_sha256": file_checksum(MIGRATION),
            "all_original_values_preserved": True, "tables_checked": len(expected),
            "preserved": preserved}


@app.command()
def drill(checkpoint: Path, report: Path = Path("docs/Phase5_Restored_Migration.json")):
    backup = json.loads(checkpoint.read_text())
    dump = checkpoint.parent / backup["dump_file"]
    if file_checksum(dump) != backup["dump_sha256"]:
        raise ValueError("Checkpoint dump changed")
    _validate_archived_files(checkpoint.parent, backup)
    with PostgresSandbox("phase5-restore", use_tmpfs=False) as sandbox:
        database = "caf_phase5_restore"
        sandbox.allow(database)
        admin = sa.create_engine(sandbox.url(), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                connection.execute(sa.text(f"CREATE DATABASE {database}"))
        finally:
            admin.dispose()
        url = sandbox.url(database)
        _pg_command("pg_restore", url, ["--no-owner", "--no-acl", "--exit-on-error", str(dump)])
        engine = sa.create_engine(url)
        try:
            with engine.begin() as connection:
                if database_content(connection) != backup["tables"]:
                    raise ValueError("Restored row hashes differ")
                if compare_schema_snapshots(backup["schema"], schema_snapshot(connection)):
                    raise ValueError("Restored schema differs")
                result = migrate(connection)
                result.update(checkpoint=str(checkpoint), dump_sha256=backup["dump_sha256"],
                              restored_exact=True, archived_files_verified=True,
                              archived_file_count=len(backup["files"]))
        finally:
            engine.dispose()
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Restored migration verified: {report}")


@app.command()
def apply(commit: bool = typer.Option(False, "--commit"),
          drill_report: Path = Path("docs/Phase5_Restored_Migration.json"),
          report: Path = Path("docs/Phase5_Normal_Migration.json")):
    if not commit:
        with get_engine("migration").connect() as connection:
            typer.echo(json.dumps({"current_revision": connection.scalar(sa.text(
                "SELECT version_num FROM ops.alembic_version")), "target_revision": HEAD,
                "migration_sha256": file_checksum(MIGRATION), "database_changed": False}, indent=2))
        return
    verified = json.loads(drill_report.read_text())
    if not all(verified.get(key) for key in (
        "restored_exact", "archived_files_verified", "all_original_values_preserved"
    )) or verified["migration_sha256"] != file_checksum(MIGRATION):
        raise ValueError("Successful restored migration for this exact migration is required")
    checkpoint = Path(verified["checkpoint"])
    backup = json.loads(checkpoint.read_text())
    if file_checksum(checkpoint.parent / backup["dump_file"]) != verified["dump_sha256"]:
        raise ValueError("Recovery dump changed")
    _validate_archived_files(checkpoint.parent, backup)
    with get_engine("migration").begin() as connection:
        result = migrate(connection)
    apply_grants()
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Classification schema migrated with original-value assertions: {report}")


if __name__ == "__main__":
    app()
