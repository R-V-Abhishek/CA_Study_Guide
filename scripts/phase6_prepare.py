"""Restore a Phase 5 checkpoint before applying the published-reader migration."""

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa
import typer

from caf_common.backup import (
    _archive_tree, _pg_command, _validate_archived_files, database_content, file_checksum, verify_backup,
)
from caf_common.postgres_sandbox import PostgresSandbox
from caf_db.engine import get_engine
from caf_db.grants import apply_grants
from caf_db.schema_baseline import schema_snapshot, compare_schema_snapshots
from phase3_prepare import original_snapshot, preserved_content

app = typer.Typer(pretty_exceptions_show_locals=False)
HEAD = "0007_question_reader"
MIGRATION = Path(f"packages/db/caf_db/alembic/versions/{HEAD}.py")


def frozen_artifacts() -> dict:
    """Fingerprint retained Phase 5 experiments; exclude transient operator locks."""
    import hashlib
    root=Path('artifacts/phase5')
    files={str(path):file_checksum(path) for path in sorted(root.rglob('*'))
           if path.is_file() and path.suffix in {'.json','.jsonl','.md','.csv'}}
    digest=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    return {'root':str(root),'file_count':len(files),'sha256':digest}


@app.command()
def archive_experiments(checkpoint: Path):
    """Complete a fresh checkpoint with the immutable experiment file inventory."""
    backup=json.loads(checkpoint.read_text())
    if 'frozen_artifacts' in backup:
        if backup['frozen_artifacts']!=frozen_artifacts():
            raise ValueError('Frozen artifacts changed since this checkpoint')
        _validate_archived_files(checkpoint.parent,backup)
        typer.echo('Frozen experiments already archived and verified')
        return
    files=_archive_tree(Path('artifacts/phase5'),checkpoint.parent/'configs'/'artifacts'/'phase5',checkpoint.parent)
    backup['files'].update(files)
    backup['frozen_artifacts']=frozen_artifacts()
    checkpoint.write_text(json.dumps(backup,indent=2)+'\n')
    _validate_archived_files(checkpoint.parent,backup)
    typer.echo(f'Archived and verified {len(files)} experiment files')


@app.command()
def state():
    """Inspect review readiness without exposing credentials or changing state."""
    with get_engine('migration').connect() as connection:
        release=connection.execute(sa.text('SELECT taxonomy_version_id,status,approved_by FROM ref.taxonomy_release ORDER BY taxonomy_version_id')).mappings().all()
        typer.echo(json.dumps({'releases':[dict(row) for row in release],
            'experimental_suggestions':connection.scalar(sa.text('SELECT count(*) FROM ingest.suggestion_revision WHERE experimental')),
            'reviewed_questions':connection.scalar(sa.text('SELECT count(*) FROM core.question_publication WHERE current_revision_id IS NOT NULL')),
            'revision':connection.scalar(sa.text('SELECT version_num FROM ops.alembic_version'))},indent=2))


@app.command()
def recover(checkpoint: Path, report: Path=Path('docs/Phase6_Recovery_Verification.json')):
    """Verify a post-migration checkpoint, including new evidence and experiments."""
    backup=json.loads(checkpoint.read_text())
    frozen=frozen_artifacts()
    if backup.get('frozen_artifacts')!=frozen or backup['database_revision']!=HEAD:
        raise ValueError('An archived Phase 6 checkpoint of the unchanged experiments is required')
    result=verify_backup(dump_file=checkpoint.parent/backup['dump_file'],scratch_db_name='caf_verify_phase6')
    if not result.verified:
        raise ValueError(result.message)
    summary={'checkpoint':str(checkpoint),'dump_sha256':backup['dump_sha256'],
        'revision':backup['database_revision'],'verified':result.verified,'restore_report':str(result.report_file),
        'tables_checked':len(result.restored_counts),'archived_files_verified':True,'archived_file_count':len(backup['files']),
        'frozen_artifacts':frozen,'frozen_artifacts_preserved':frozen_artifacts()==frozen,
        'restored_counts':result.restored_counts}
    report.write_text(json.dumps(summary,indent=2)+'\n')
    typer.echo(f'Complete Phase 6 recovery verified: {report}')


def migrate(connection):
    before = original_snapshot(connection)
    revision = connection.scalar(sa.text("SELECT version_num FROM ops.alembic_version"))
    if revision not in {"0006_classification_revisions", HEAD}:
        raise ValueError(f"Expected the Phase 5 schema; found {revision}")
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, HEAD)
    preserved = preserved_content(connection, before)
    expected = {name: value for name, value in before["tables"].items()
                if name != "ops.alembic_version"}
    if preserved != expected:
        raise ValueError("Migration changed original values; transaction aborted")
    evidence = {
        "experimental_suggestions": connection.scalar(sa.text("SELECT count(*) FROM ingest.suggestion_revision WHERE experimental")),
        "classification_revisions": connection.scalar(sa.text("SELECT count(*) FROM core.classification_revision")),
        "current_reviewed_questions": connection.scalar(sa.text("SELECT count(*) FROM core.question_publication WHERE current_revision_id IS NOT NULL")),
        "published_snapshots": connection.scalar(sa.text("SELECT count(*) FROM core.published_question")),
        "corpus_generation": connection.scalar(sa.text("SELECT generation FROM core.corpus_generation WHERE id=1")),
    }
    return {"from_revision": revision, "to_revision": HEAD,
            "migration_sha256": file_checksum(MIGRATION),
            "all_original_values_preserved": True, "tables_checked": len(expected),
            "preserved": preserved, "review_state": evidence, "live_reviews_or_promotions_created": False}


@app.command()
def drill(checkpoint: Path, report: Path = Path("docs/Phase6_Restored_Migration.json")):
    backup = json.loads(checkpoint.read_text())
    frozen = frozen_artifacts()
    if backup.get('frozen_artifacts')!=frozen:
        raise ValueError('Archive the unchanged frozen experiments in this checkpoint first')
    dump = checkpoint.parent / backup["dump_file"]
    if file_checksum(dump) != backup["dump_sha256"]:
        raise ValueError("Checkpoint dump changed")
    _validate_archived_files(checkpoint.parent, backup)
    with PostgresSandbox("phase6-restore", use_tmpfs=False) as sandbox:
        database = "caf_phase6_restore"
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
                              archived_file_count=len(backup["files"]),
                              frozen_artifacts=frozen, frozen_artifacts_preserved=frozen_artifacts()==frozen)
        finally:
            engine.dispose()
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Restored migration verified: {report}")


@app.command()
def apply(commit: bool = typer.Option(False, "--commit"),
          drill_report: Path = Path("docs/Phase6_Restored_Migration.json"),
          report: Path = Path("docs/Phase6_Normal_Migration.json")):
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
    frozen=frozen_artifacts()
    if frozen!=verified["frozen_artifacts"]:
        raise ValueError("Frozen experiment files changed since the restored drill")
    with get_engine("migration").begin() as connection:
        result = migrate(connection)
    apply_grants()
    result.update(frozen_artifacts=frozen, frozen_artifacts_preserved=frozen_artifacts()==frozen, checkpoint=str(checkpoint))
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(f"Reader schema migrated with original-value assertions: {report}")


if __name__ == "__main__":
    app()
