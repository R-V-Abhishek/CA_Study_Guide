"""Exercise the real Linux shell launcher with a newly built application image."""

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import typer

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def verify(image: str = typer.Option(...)) -> None:
    if sys.platform != "linux":
        typer.echo("SKIP: host launcher requires Linux; native Linux CI exercises it")
        return
    root = Path(__file__).resolve().parents[1]
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    environment["CAF_HOST_IMAGE"] = image
    environment["CAF_HOST_TEST_CANARY"] = "do-not-export-this-host-environment"
    result = subprocess.run(["sh", str(root / "deploy/caf-host"), "preflight"], env=environment,
                            capture_output=True, text=True, timeout=300)
    if result.returncode not in {0, 2}:
        raise RuntimeError(f"Host launcher failed: {result.stderr[-2000:]}")
    report = json.loads(result.stdout)
    identity = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    assert report["tool_image"] == identity
    assert report["format_version"] == 1 and report["platform"].startswith("linux/")
    assert report["cpu_threads"] > 0 and report["free_storage_bytes"] > 0
    assert environment["CAF_HOST_TEST_CANARY"] not in result.stdout
    typer.echo("PASS: packaged host launcher, actual Linux probes, redacted report, no service changes")
    from caf_common.backup import critical_tables

    with tempfile.TemporaryDirectory(prefix="caf-inspect-backup-") as temporary:
        snapshot = Path(temporary)
        dump = b"synthetic fixture; not a PostgreSQL dump"
        (snapshot / "fixture.dump").write_bytes(dump)
        (snapshot / "manifest.json").write_text(json.dumps({
            "format_version": 1, "created_at": "2026-10-20T10:00:00+00:00",
            "database_revision": "0009_question_language", "dump_file": "fixture.dump",
            "dump_sha256": hashlib.sha256(dump).hexdigest(),
            "tables": {table: {"count": 0, "sha256": "a" * 64}
                       for table in critical_tables("0009_question_language")},
            "schema": {}, "files": {}, "digest_format": "fixture", "secrets": "fixture",
        }))
        command = ["sh", str(root / "deploy/caf-host"), "inspect-backup", str(snapshot)]
        inspected = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
        if inspected.returncode:
            raise RuntimeError(f"Backup inspection launcher failed: {inspected.stderr[-2000:]}")
        evidence = json.loads(inspected.stdout)
        assert evidence["file_integrity_verified"] and evidence["restore_verified"] is False
        assert environment["CAF_HOST_TEST_CANARY"] not in inspected.stdout
        assert set(path.name for path in snapshot.iterdir()) == {"fixture.dump", "manifest.json"}
        (snapshot / "fixture.dump").write_bytes(b"corrupted")
        rejected = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
        assert rejected.returncode == 1 and "Dump checksum mismatch" in rejected.stderr
    typer.echo("PASS: packaged backup inspection, corruption rejection, no restore claim or snapshot writes")


if __name__ == "__main__":
    app()
