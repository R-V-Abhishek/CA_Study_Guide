"""File-format and Git guards; no production configuration or Docker access."""

from datetime import datetime, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from release_bundle import (
    FileRecord, ImageRecord, Manifest, PAYLOAD, app, digest, source_identity, verify_archive,
)


def bundle_fixture(tmp_path, *, overrides=None, extra=None):
    files = {name: b"synthetic payload" for name in PAYLOAD}
    manifest = Manifest(version="v0.2.0", candidate=True, commit="a" * 40,
        platform="linux/amd64", created_at=datetime.now(timezone.utc),
        application=ImageRecord(reference="caf:v0.2.0-candidate-aaaaaaaaaaaa-amd64", image_id="sha256:" + "b" * 64),
        postgres=ImageRecord(reference="caf-postgres:" + "c" * 64, image_id="sha256:" + "c" * 64),
        required_schema="0009_question_language", supported_schemas=["0009_question_language"],
        dependency_locks={"uv.lock": "d" * 64, "web/pnpm-lock.yaml": "e" * 64},
        files={name: FileRecord(sha256=hashlib.sha256(value).hexdigest(), size=len(value))
               for name, value in files.items()})
    if overrides:
        manifest = manifest.model_copy(update=overrides)
    files["manifest.json"] = manifest.model_dump_json().encode()
    files["SHA256SUMS"] = "".join(f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n"
                                  for name in sorted(files)).encode()
    if extra:
        files.update(extra)
    bundle = tmp_path / "fixture.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, value in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, BytesIO(value))
    sidecar(bundle)
    return bundle


def sidecar(bundle):
    bundle.with_name(bundle.name + ".sha256").write_text(f"{digest(bundle)}  {bundle.name}\n")


def test_bundle_round_trip_and_selection_guards(tmp_path):
    bundle = bundle_fixture(tmp_path)
    assert verify_archive(bundle).required_schema == "0009_question_language"
    runner = CliRunner()
    assert runner.invoke(app, ["verify", str(bundle)]).exit_code != 0
    assert runner.invoke(app, ["verify", str(bundle), "--allow-candidate", "--platform", "linux/arm64"]).exit_code != 0
    assert runner.invoke(app, ["verify", str(bundle), "--allow-candidate", "--platform", "linux/amd64"]).exit_code == 0


def test_corrupted_outer_archive(tmp_path):
    bundle = bundle_fixture(tmp_path)
    with bundle.open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(ValueError, match="Outer bundle"):
        verify_archive(bundle)


@pytest.mark.parametrize("name", ["../escape", "/etc/caf/secret", "unexpected.txt"])
def test_unexpected_archive_paths(tmp_path, name):
    bundle = bundle_fixture(tmp_path, extra={name: b"must not extract"})
    with pytest.raises(ValueError, match="bundle members"):
        verify_archive(bundle)
    assert not (tmp_path.parent / "escape").exists()


@pytest.mark.parametrize("kind", ["duplicate", "symlink", "payload", "checksums"])
def test_invalid_members_and_inner_hashes(tmp_path, kind):
    bundle = bundle_fixture(tmp_path)
    with tarfile.open(bundle, "r:gz") as archive:
        members = [(member, archive.extractfile(member).read()) for member in archive.getmembers()]
    with tarfile.open(bundle, "w:gz") as archive:
        for member, value in members:
            if member.name == "images.tar":
                if kind == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "/etc/caf/secret"
                    member.size = 0
                elif kind == "payload":
                    value = b"altered payload!!"
                    member.size = len(value)
            if member.name == "SHA256SUMS" and kind == "checksums":
                value = b"0" + value[1:]
            archive.addfile(member, BytesIO(value))
            if kind == "duplicate" and member.name == "images.tar":
                archive.addfile(member, BytesIO(value))
    sidecar(bundle)
    with pytest.raises(ValueError):
        verify_archive(bundle)


@pytest.mark.parametrize("override", [
    {"supported_schemas": []}, {"dependency_locks": {}},
    {"application": ImageRecord(reference="caf:wrong", image_id="sha256:" + "b" * 64)},
])
def test_invalid_manifest_contract(tmp_path, override):
    bundle = bundle_fixture(tmp_path, overrides=override)
    with pytest.raises(ValueError):
        verify_archive(bundle)


def test_clean_source_version_tag_and_lock_guards(tmp_path):
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=tmp_path, text=True).strip()
    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Synthetic fixture")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "0.2.0"\n')
    (tmp_path / "uv.lock").write_text('[[package]]\nname = "fixture"\nversion = "0.2.0"\n')
    git("add", ".")
    git("commit", "-qm", "fixture")
    identity = source_identity(tmp_path, candidate=True)
    assert identity == ("v0.2.0", git("rev-parse", "HEAD"))
    with pytest.raises(subprocess.CalledProcessError):
        source_identity(tmp_path, candidate=False)
    git("tag", "v0.2.0")
    assert source_identity(tmp_path, candidate=False) == identity
    (tmp_path / "untracked").write_text("not accepted")
    with pytest.raises(ValueError, match="clean working tree"):
        source_identity(tmp_path, candidate=True)
    git("add", ".")
    git("commit", "-qm", "new commit")
    with pytest.raises(ValueError, match="tag must point"):
        source_identity(tmp_path, candidate=False)
    (tmp_path / "uv.lock").write_text('[[package]]\nname = "fixture"\nversion = "0.1.0"\n')
    git("add", ".")
    git("commit", "-qm", "mismatch")
    with pytest.raises(ValueError, match="differs from uv.lock"):
        source_identity(tmp_path, candidate=True)
