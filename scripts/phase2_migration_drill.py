"""Restore a checkpoint, migrate it, and prove every preexisting value survived."""

import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
import typer

from caf_common.backup import _pg_command, database_content, file_checksum
from caf_common.postgres_sandbox import PostgresSandbox

app = typer.Typer()

ADDED_COLUMNS = {
    "app.user_account": ["issuer", "subject", "email", "email_verified", "role", "status"],
    "app.settings": ["selected_paper_ids"],
    "core.decision": ["actor_id"],
}


def original_content(connection, tables):
    connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
    result = {}
    for table in tables:
        columns = ADDED_COLUMNS.get(table, [])
        expression = "to_jsonb(t)" + "".join(f" - '{column}'" for column in columns)
        where = " WHERE id <> '2027-05'" if table == "ref.attempt" else ""
        rows = connection.execute(sa.text(
            f"SELECT ({expression})::text FROM {table} t{where} ORDER BY ({expression})::text COLLATE \"C\""
        ))
        digest = hashlib.sha256()
        count = 0
        for row in rows:
            digest.update(row[0].encode() + b"\n")
            count += 1
        result[table] = {"count": count, "sha256": digest.hexdigest()}
    return result


@app.command()
def drill(manifest_file: Path, report: Path = Path("docs/Phase2_Restored_Migration.json")):
    manifest = json.loads(manifest_file.read_text())
    dump = manifest_file.parent / manifest["dump_file"]
    assert file_checksum(dump) == manifest["dump_sha256"]
    with PostgresSandbox("phase2-restore") as sandbox:
        sandbox.allow("caf_phase2_restore")
        admin = sa.create_engine(sandbox.url(), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                connection.execute(sa.text("CREATE DATABASE caf_phase2_restore"))
        finally:
            admin.dispose()
        url = sandbox.url("caf_phase2_restore")
        _pg_command("pg_restore", url, ["--no-owner", "--no-acl", "--exit-on-error", str(dump)])
        engine = sa.create_engine(url)
        try:
            with engine.begin() as connection:
                before = database_content(connection)
                assert before == manifest["tables"], "Restored checkpoint differs"
                original_tables = [table for table in before if table != "ops.alembic_version"]
                config = Config("alembic.ini")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                preserved = original_content(connection, original_tables)
                expected = {table: before[table] for table in original_tables}
                assert preserved == expected, "Migration changed preexisting values"
                accounts = connection.execute(sa.text("SELECT id,status,issuer,subject FROM app.user_account ORDER BY id")).mappings().all()
                assert all(row["status"] == "pending_binding" and row["issuer"] is None and row["subject"] is None for row in accounts)
                next_id = connection.execute(sa.text("SELECT nextval(pg_get_serial_sequence('app.user_account','id'))")).scalar_one()
                assert next_id > max((row["id"] for row in accounts), default=0)
                new_tables = sorted(set(database_content(connection)) - set(before))
                assert set(new_tables) == {"app.invitation", "app.login_transaction", "app.auth_session"}
                report.write_text(json.dumps({"checkpoint": str(manifest_file), "restored_exact": True,
                    "all_original_values_preserved": True, "tables_checked": len(expected),
                    "legacy_accounts": [dict(row) for row in accounts], "next_account_id": next_id,
                    "new_tables": new_tables, "preserved": preserved}, indent=2, default=str) + "\n")
        finally:
            engine.dispose()
    typer.echo(f"Restored migration passed: {report}")


if __name__ == "__main__":
    app()
