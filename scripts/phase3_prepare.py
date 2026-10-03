"""Checkpoint restore, preservation assertions, and unapproved textbook import.

This command never approves descriptors or activates a structural release.
"""

import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
import typer

from caf_common.backup import _pg_command, _validate_archived_files, database_content, file_checksum
from caf_common.postgres_sandbox import PostgresSandbox
from caf_db.engine import get_engine
from caf_db.grants import apply_grants
from caf_l0.manifest import load_manifest
from caf_l0.releases import digest, import_release, release_report

app = typer.Typer(pretty_exceptions_show_locals=False)
HEAD = "0004_textbook_taxonomy"


def original_snapshot(connection) -> dict:
    tables = database_content(connection)
    inspector = sa.inspect(connection)
    columns = {}
    for table in tables:
        schema, name = table.split(".")
        columns[table] = [column["name"] for column in inspector.get_columns(name, schema=schema)]
    return {"tables": tables, "columns": columns,
            "legacy_node_ids": list(connection.scalars(sa.text("SELECT id FROM ref.node ORDER BY id"))),
            "legacy_doc_types": list(connection.scalars(sa.text("SELECT id FROM ref.doc_type ORDER BY id"))),
            "max_taxonomy_id": connection.scalar(sa.text("SELECT COALESCE(max(id),0) FROM ref.taxonomy_version"))}


def preserved_content(connection, snapshot: dict) -> dict:
    """Compare original columns/rows while permitting append-only draft records."""
    connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
    quote = connection.dialect.identifier_preparer.quote
    result = {}
    for table, columns in snapshot["columns"].items():
        if table == "ops.alembic_version":
            continue
        schema, name = table.split(".")
        projection = ",".join(quote(column) for column in columns)
        predicate = ""
        params = {}
        if table == "ref.node":
            predicate = " WHERE id=ANY(:ids)"
            params["ids"] = snapshot["legacy_node_ids"]
        elif table == "ref.doc_type":
            predicate = " WHERE id=ANY(:ids)"
            params["ids"] = snapshot["legacy_doc_types"]
        elif table == "ref.taxonomy_version":
            predicate = " WHERE id<=:maximum"
            params["maximum"] = snapshot["max_taxonomy_id"]
        sql = f'SELECT to_jsonb(t)::text FROM (SELECT {projection} FROM {quote(schema)}.{quote(name)}{predicate}) t ORDER BY to_jsonb(t)::text COLLATE "C"'
        hasher = hashlib.sha256()
        count = 0
        for row in connection.execute(sa.text(sql), params):
            hasher.update(row[0].encode() + b"\n")
            count += 1
        result[table] = {"count": count, "sha256": hasher.hexdigest()}
    return result


def migrate_and_import(connection, manifest: dict) -> dict:
    before = original_snapshot(connection)
    revision = connection.scalar(sa.text("SELECT version_num FROM ops.alembic_version"))
    if revision not in {"0003_identity", HEAD}:
        raise ValueError(f"Expected the Phase 2 database or current Phase 3 head; got {revision}")
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, HEAD)
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        imported = import_release(session, manifest, dry_run=False)
        session.commit()
    after = preserved_content(connection, before)
    expected = {table: value for table, value in before["tables"].items() if table != "ops.alembic_version"}
    if after != expected:
        changed = sorted(table for table in expected if after.get(table) != expected[table])
        raise ValueError("Original values changed; transaction aborted: " + ", ".join(changed))
    return {"from_revision": revision, "to_revision": HEAD,
            "all_original_values_preserved": True, "tables_checked": len(expected),
            "preserved": after, "release": imported, "activation_performed": False}


@app.command("plan")
def plan(manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json")):
    from caf_l0.releases import validate_manifest
    typer.echo(json.dumps(validate_manifest(load_manifest(manifest_path)), indent=2))


@app.command("drill")
def drill(checkpoint: Path, manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json"),
          report: Path = Path("docs/Phase3_Restored_Migration.json")):
    backup = json.loads(checkpoint.read_text())
    dump = checkpoint.parent / backup["dump_file"]
    if file_checksum(dump) != backup["dump_sha256"]:
        raise ValueError("Checkpoint dump checksum mismatch")
    _validate_archived_files(checkpoint.parent, backup)
    manifest = load_manifest(manifest_path)
    with PostgresSandbox("phase3-restore") as sandbox:
        database = "caf_phase3_restore"
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
                    raise ValueError("Restored checkpoint row hashes differ")
                result = migrate_and_import(connection, manifest)
                result.update(checkpoint=str(checkpoint), dump_sha256=backup["dump_sha256"],
                              manifest_hash=digest(manifest), restored_exact=True)
                result["archived_files_verified"] = True
        finally:
            engine.dispose()
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Restored checkpoint and draft import verified: {report}")


@app.command("apply")
def apply(manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json"),
          drill_report: Path = Path("docs/Phase3_Restored_Migration.json"),
          report: Path = Path("docs/Phase3_Normal_Migration.json"),
          commit: bool = typer.Option(False, "--commit")):
    manifest = load_manifest(manifest_path)
    if not commit:
        from caf_l0.releases import validate_manifest
        typer.echo(json.dumps({**validate_manifest(manifest), "database_changed": False}, indent=2))
        return
    verified = json.loads(drill_report.read_text())
    if not verified["restored_exact"] or not verified["archived_files_verified"] or not verified["all_original_values_preserved"] or verified["manifest_hash"] != digest(manifest):
        raise ValueError("A successful restored migration for this exact manifest is required")
    checkpoint = Path(verified["checkpoint"])
    backup = json.loads(checkpoint.read_text())
    if file_checksum(checkpoint.parent / backup["dump_file"]) != verified["dump_sha256"]:
        raise ValueError("Verified recovery checkpoint is unavailable or changed")
    _validate_archived_files(checkpoint.parent, backup)
    with get_engine("migration").begin() as connection:
        result = migrate_and_import(connection, manifest)
    apply_grants()
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Schema and unapproved draft imported with original-value assertions: {report}")


if __name__ == "__main__":
    try:
        app()
    except DBAPIError as error:
        typer.echo(f"Database operation failed: {error.orig}", err=True)
        raise SystemExit(1) from None
