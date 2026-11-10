"""caf-host content refuses malformed requests before it touches Docker or the installation."""

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def content(*arguments, root=None):
    return subprocess.run(
        [
            "sh",
            str(ROOT / "deploy/caf-host"),
            "content",
            *arguments,
            *(["--root", str(root)] if root else []),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    "script", ["content-host.sh", "lib.sh", "upgrade-host.sh", "backup-host.sh"]
)
def test_host_scripts_parse(script):
    assert subprocess.run(["bash", "-n", str(ROOT / "deploy" / script)]).returncode == 0


@pytest.mark.parametrize(
    "arguments, message",
    [
        ((), "Usage: caf-host content"),
        (("publish",), "Usage: caf-host content"),
        (("import",), "Usage: caf-host content"),
        (("import", "a.tar.gz", "b.tar.gz"), "Usage: caf-host content"),
        (("import", "a.tar.gz", "--limit", "1"), "Usage: caf-host content"),
        (("extract",), "Usage: caf-host content"),
        (("extract", "--limit", "0"), "positive whole number"),
        (("extract", "--doc", "1; rm -rf /"), "positive whole number"),
        (("extract", "--limit", "1", "--name", "x"), "Usage: caf-host content"),
        (("extract", "--limit", "1", "--profile", "x.yaml"), "Unknown content option: --profile"),
        (("classify-export", "--taxonomy", "textbook-2026-10"), "Usage: caf-host content"),
        (("classify-export", "--taxonomy", "--doc", "--revision", "1"), "Invalid taxonomy"),
        (
            ("classify-export", "--revision", "1", "--taxonomy", "t", "--name", "Bad/Name"),
            "Invalid batch name",
        ),
        (("classify-import", "batch.json"), "Usage: caf-host content"),
    ],
)
def test_malformed_requests_are_refused(arguments, message):
    result = content(*arguments)
    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.skipif(
    not (shutil.which("flock") and shutil.which("jq")), reason="needs Linux host tools"
)
def test_import_requires_an_active_installation(tmp_path):
    bundle = tmp_path / ("content-" + "0" * 12 + ".tar.gz")
    bundle.write_bytes(b"")
    result = content("import", str(bundle), root=tmp_path)
    assert result.returncode == 1
    assert "An active installation is required" in result.stderr
    assert not (tmp_path / "content").exists() and not (tmp_path / ".content.lock").exists()


def test_sandboxed_verify_has_writable_storage():
    # The image links /app/data to /srv/caf/data, and caf creates storage directories on start.
    script = (ROOT / "deploy/content-host.sh").read_text()
    verify = script[script.index('docker run "${sandbox[@]}"') :].split("content verify")[0]
    assert "--tmpfs /srv/caf/data:" in verify
