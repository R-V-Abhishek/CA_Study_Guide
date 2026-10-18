"""Recovery failure paths exercise real PostgreSQL and source-independent manifests."""

from datetime import datetime, timezone
import json
import subprocess

import pytest
import sqlalchemy as sa
from caf_common import backup
from caf_common.settings import get_settings
from caf_db.engine import get_engine
from caf_db.models.app import Note, Progress, StudySession
from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_common.postgres_sandbox import PostgresSandbox


def test_successive_schema_revisions_preserve_required_backup_tables():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations = ScriptDirectory.from_config(Config("alembic.ini"))
    for migration in migrations.walk_revisions():
        if migration.down_revision:
            assert backup.critical_tables(migration.revision) >= backup.critical_tables(migration.down_revision)


def test_disk_backed_recovery_storage_is_writable_and_removed_with_its_container():
    with PostgresSandbox('disk-recovery-test',use_tmpfs=False) as sandbox:
        mounts=json.loads(subprocess.run(['docker','inspect','--format','{{json .Mounts}}',sandbox.name],
            check=True,capture_output=True,text=True).stdout)
        storage=next(mount for mount in mounts if mount['Destination']=='/var/lib/postgresql/data')
        assert storage['Type']=='volume'
        owned_volume=storage['Name']
        engine=sa.create_engine(sandbox.url())
        try:
            with engine.begin() as connection:
                connection.execute(sa.text('CREATE TABLE recovery_marker(value text)'))
                connection.execute(sa.text("INSERT INTO recovery_marker VALUES ('isolated recovery storage')"))
                assert connection.execute(sa.text('SELECT value FROM recovery_marker')).scalar_one()=='isolated recovery storage'
        finally:
            engine.dispose()
    removed=subprocess.run(['docker','volume','inspect',owned_volume],capture_output=True,text=True)
    assert removed.returncode!=0 and 'no such volume' in removed.stderr.lower()


def seed_protected_records(session):
    now = datetime.now(timezone.utc)
    node = "P1-WB29V3"
    session.add_all([
        Progress(user_id=1, node_id=node, status="done"),
        Note(user_id=1, node_id=node, body="Recovery checkpoint note"),
        StudySession(user_id=1, node_id=node, started_at=now, minutes=37),
    ])
    decision = Decision(unit_fingerprint="recovery-fixture", action="accept", payload={}, blind=False)
    session.add(decision)
    session.flush()
    appearance = Appearance(unit_fingerprint="recovery-fixture", doc_sha256="fixture-checksum",
                            attempt_id="2024-05", source_paper_id="s2023.P1",
                            doc_type_id="suggested_answer", signal_class="exam",
                            display_label="1(a)", gist="Recovery fixture", page_start=1, page_end=1,
                            status="published")
    session.add(appearance)
    session.flush()
    session.add(AppearanceTag(appearance_id=appearance.id, node_id=node, role="primary",
                              share=1.0, decision_id=decision.id))
    session.commit()
    blob = get_settings().storage.blob_dir / "fixture.pdf"
    blob.write_bytes(b"recovery-source-blob")


def artifact(session, tmp_path):
    seed_protected_records(session)
    return backup.create_backup(backup_dir=tmp_path)


def test_protected_content_survives_and_live_changes_do_not_affect_verification(session, tmp_path):
    manifest = artifact(session, tmp_path)
    data = json.loads(manifest.manifest_file.read_text())
    for table in ("app.progress", "app.note", "app.study_session", "core.decision", "core.appearance"):
        assert data["tables"][table]["count"] == 1
    # The source database evolves after capture; verification must use the manifest.
    session.get(Note, (1, "P1-WB29V3")).body = "Changed after capture"
    session.add(StudySession(user_id=1, started_at=datetime.now(timezone.utc), minutes=12))
    session.commit()
    result = backup.verify_backup(dump_file=manifest.dump_file)
    assert result.verified, result.message
    assert result.restored_counts["app.study_session"] == 1
    assert result.restored_counts == result.live_counts
    assert json.loads(result.report_file.read_text())["verified"] is True
    archived_settings = (manifest.backup_dir / "configs/config/settings.toml").read_text()
    assert 'password = "[REDACTED]"' in archived_settings
    assert "postgres_dev_password" not in archived_settings


@pytest.mark.parametrize("failure", ["corrupt_dump", "unreadable_dump", "altered_file", "missing_file", "missing_table", "changed_digest", "restore_failure"])
def test_recovery_failures_are_explicit(session, tmp_path, monkeypatch, failure):
    manifest = artifact(session, tmp_path)
    data = json.loads(manifest.manifest_file.read_text())
    if failure in {"corrupt_dump", "unreadable_dump"}:
        manifest.dump_file.write_bytes(b"not a postgres dump")
        if failure == "unreadable_dump":
            # Let checksum validation pass to exercise pg_restore's format failure.
            data["dump_sha256"] = backup.file_checksum(manifest.dump_file)
    elif failure in {"altered_file", "missing_file"}:
        file = manifest.backup_dir / "blobs/fixture.pdf"
        if failure == "altered_file":
            file.write_bytes(b"altered source")
        else:
            file.unlink()
    elif failure == "missing_table":
        # A valid dump without a required table must fail even when pg_restore succeeds.
        backup._pg_command("pg_dump", backup._database_url(), ["--format=custom", "--exclude-table=app.note", "--file", str(manifest.dump_file)])
        data["dump_sha256"] = backup.file_checksum(manifest.dump_file)
    elif failure == "changed_digest":
        data["tables"]["app.note"]["sha256"] = "0" * 64
    else:
        run = subprocess.run
        def fail_restore(command, **kwargs):
            if command[0] == "pg_restore":
                raise subprocess.CalledProcessError(1, command, stderr="forced restore failure")
            return run(command, **kwargs)
        monkeypatch.setattr(subprocess, "run", fail_restore)
    manifest.manifest_file.write_text(json.dumps(data))
    result = backup.verify_backup(dump_file=manifest.dump_file)
    assert not result.verified
    assert result.mismatches
    assert "failed" in result.message.lower()
    assert json.loads(result.report_file.read_text())["verified"] is False


def test_existing_scratch_database_is_preserved(session, tmp_path, isolated_database):
    manifest = artifact(session, tmp_path)
    sandbox = isolated_database
    name = "caf_verify_existing"
    sandbox.allow(name)
    admin = sa.create_engine(sandbox.url(), isolation_level="AUTOCOMMIT")
    scratch = sa.create_engine(sandbox.url(name))
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
        with scratch.begin() as conn:
            conn.execute(sa.text("CREATE TABLE marker(value text)"))
            conn.execute(sa.text("INSERT INTO marker VALUES ('preserve me')"))
        with pytest.raises(ValueError, match="preserved"):
            backup.verify_backup(dump_file=manifest.dump_file, scratch_db_name=name)
        with scratch.connect() as conn:
            assert conn.execute(sa.text("SELECT value FROM marker")).scalar_one() == "preserve me"
    finally:
        scratch.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.mark.parametrize("name", ["caf", "postgres", "caf_verify; DROP DATABASE caf", "other_db"])
def test_unsafe_scratch_names_rejected(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe"):
        backup.verify_backup(dump_file=tmp_path / "none.dump", scratch_db_name=name)


def test_legacy_backups_not_claimed_verified(tmp_path):
    dump = tmp_path / "caf_legacy.dump"
    dump.write_bytes(b"legacy")
    assert backup.list_backups(tmp_path)[0]["legacy"]
    result = backup.verify_backup(dump_file=dump)
    assert not result.verified
    assert "Legacy" in result.message


def test_backup_uses_same_exported_snapshot_when_source_changes_during_dump(session, tmp_path, monkeypatch):
    seed_protected_records(session)
    original = backup._pg_command
    def change_source_then_dump(binary, url, arguments):
        if binary == "pg_dump":
            with get_engine().begin() as conn:
                conn.execute(sa.text("UPDATE app.note SET body = 'Modified during pg_dump'"))
        return original(binary, url, arguments)
    monkeypatch.setattr(backup, "_pg_command", change_source_then_dump)
    manifest = backup.create_backup(backup_dir=tmp_path)
    result = backup.verify_backup(dump_file=manifest.dump_file)
    assert result.verified, result.message


def test_recovery_digests_independent_of_source_database_timezone(session, tmp_path):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text(f'ALTER DATABASE "{engine.url.database}" SET timezone = \'Asia/Kolkata\''))
    seed_protected_records(session)
    manifest = backup.create_backup(backup_dir=tmp_path)
    result = backup.verify_backup(dump_file=manifest.dump_file)
    assert result.verified, result.message
