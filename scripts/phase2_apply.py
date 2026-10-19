"""Apply the tested identity migration while asserting legacy values in one transaction."""

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
import typer

from caf_common.backup import database_content
from caf_db.engine import get_engine
from phase2_migration_drill import original_content

app = typer.Typer()


@app.command()
def migrate(apply: bool = typer.Option(False, "--apply"), report: Path = Path("docs/Phase2_Normal_Migration.json")):
    if not apply:
        raise typer.BadParameter("Use --apply after verifying a fresh checkpoint and restored migration")
    engine = get_engine("migration")
    with engine.begin() as connection:
        revision = connection.execute(sa.text("SELECT version_num FROM ops.alembic_version")).scalar_one()
        if revision != "0002_score_config_snapshot":
            raise typer.BadParameter(f"Expected Phase 1 database; got {revision}")
        before = database_content(connection)
        tables = [table for table in before if table != "ops.alembic_version"]
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        after = original_content(connection, tables)
        assert after == {table: before[table] for table in tables}, "Original values changed; transaction aborted"
        accounts = connection.execute(sa.text("SELECT id,name,status FROM app.user_account ORDER BY id")).mappings().all()
        assert all(account["status"] == "pending_binding" for account in accounts)
        assert connection.execute(sa.text("SELECT count(*) FROM app.invitation")).scalar_one() == 0
        assert connection.execute(sa.text("SELECT count(*) FROM app.auth_session")).scalar_one() == 0
        assert connection.execute(sa.text("SELECT count(*) FROM core.decision WHERE actor_id IS NOT NULL")).scalar_one() == 0
        result = {"from_revision": revision, "to_revision": "0003_identity", "preserved_table_count": len(tables),
                  "all_original_values_preserved": True, "accounts": [dict(row) for row in accounts],
                  "preserved": after}
    report.write_text(json.dumps(result, indent=2, default=str) + "\n")
    typer.echo(f"Migration committed with preservation assertions: {report}")


if __name__ == "__main__":
    app()
