"""Offline recovery inspection never connects to PostgreSQL or changes a snapshot."""

import json
import os

import pytest
from typer.testing import CliRunner

from caf_cli.host import app
from caf_common.backup import critical_tables
from caf_common.recovery_manifest import checksum, inspect_recovery_files


@pytest.fixture
def snapshot(tmp_path):
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs/source.pdf").write_bytes(b"PRIVATE_DOCUMENT_BYTES")
    (tmp_path / "caf_fixture.dump").write_bytes(b"SYNTHETIC_NOT_A_REAL_PG_DUMP")
    manifest = {
        "format_version": 1, "created_at": "2026-10-20T10:00:00+00:00",
        "database_revision": "0009_question_language", "dump_file": "caf_fixture.dump",
        "dump_sha256": checksum(tmp_path / "caf_fixture.dump"),
        "tables": {table: {"count": 0, "sha256": "a" * 64}
                   for table in critical_tables("0009_question_language")},
        "schema": {}, "files": {"blobs/source.pdf": checksum(tmp_path / "blobs/source.pdf")},
        "digest_format": "fixture", "secrets": "fixture",
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def change_manifest(snapshot, **values):
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(values)
    path.write_text(json.dumps(manifest))


def test_inspection_is_read_only_and_does_not_claim_restore(snapshot, monkeypatch):
    import sqlalchemy
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("Offline inspection attempted database or process access")

    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setenv("PGPASSWORD", "PRIVATE_PASSWORD")
    before = {str(p.relative_to(snapshot)): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in snapshot.rglob("*") if p.is_file()}
    result = CliRunner().invoke(app, ["inspect-backup", str(snapshot)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["file_integrity_verified"] and report["restore_verified"] is False
    assert report["archived_files"] == 1
    assert "PRIVATE" not in result.output
    assert before == {str(p.relative_to(snapshot)): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in snapshot.rglob("*") if p.is_file()}


@pytest.mark.parametrize("failure", ["dump", "missing", "unexpected", "file", "symlink", "directory_symlink", "fifo", "legacy", "tables", "structure"])
def test_bad_artifacts_fail_without_restore_claim(snapshot, failure):
    blob = snapshot / "blobs/source.pdf"
    if failure == "dump":
        (snapshot / "caf_fixture.dump").write_bytes(b"changed")
    elif failure == "missing":
        blob.unlink()
    elif failure == "unexpected":
        (snapshot / "blobs/extra.pdf").write_bytes(b"extra")
    elif failure == "file":
        blob.write_bytes(b"changed")
    elif failure == "symlink":
        blob.unlink()
        blob.symlink_to(snapshot / "caf_fixture.dump")
    elif failure == "directory_symlink":
        (snapshot / "configs").symlink_to(snapshot / "blobs", target_is_directory=True)
    elif failure == "fifo":
        os.mkfifo(snapshot / "blobs/pipe")
    elif failure == "legacy":
        (snapshot / "manifest.json").unlink()
    elif failure == "tables":
        change_manifest(snapshot, tables={})
    else:
        change_manifest(snapshot, dump_sha256="PRIVATE_MALFORMED_VALUE")
    result = CliRunner().invoke(app, ["inspect-backup", str(snapshot)])
    assert result.exit_code == 1, result.output
    assert "Backup inspection failed" in result.output
    assert "PRIVATE" not in result.output
    assert '"restore_verified": true' not in result.output


@pytest.mark.parametrize("name", ["../outside", "/outside", "blobs/../outside", "configs//file", "blobs\\file"])
def test_manifest_paths_cannot_escape_snapshot(snapshot, name):
    change_manifest(snapshot, files={name: "a" * 64})
    with pytest.raises(ValueError, match="Unsafe archived file path"):
        inspect_recovery_files(snapshot)


@pytest.mark.parametrize("name", ["../outside.dump", "/outside.dump", "manifest.json", "dir\\file.dump"])
def test_dump_path_cannot_escape_snapshot(snapshot, name):
    change_manifest(snapshot, dump_file=name)
    with pytest.raises(ValueError, match="Unsafe backup dump filename"):
        inspect_recovery_files(snapshot)
