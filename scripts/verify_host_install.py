"""Exercise installation from a real synthetic recovery artifact in owned host paths."""

import json
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

import typer

from caf_cli.host_bundle import verify_archive
from caf_common.recovery_manifest import checksum, inspect_recovery_files
from verify_production_compose import fixture

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def verify(bundle: Path, snapshot: Path, image: str) -> None:
    if sys.platform != "linux":
        typer.echo("SKIP: host installation is exercised on native Linux CI")
        return
    root = Path(__file__).resolve().parents[1]
    manifest = verify_archive(bundle)
    captured = inspect_recovery_files(snapshot)
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    environment["CAF_HOST_IMAGE"] = image
    with tempfile.TemporaryDirectory(prefix="caf-owned-install-") as temporary:
        base = Path(temporary)
        config = base / "compose.env"
        values = fixture()
        values.update(OIDC_CLIENT_SECRET="synthetic$literal-secret")
        config.write_text("".join(f"{key}='{value}'\n" for key, value in values.items()))
        config.chmod(0o600)
        projects = []

        def compose(target, project, *arguments):
            work = next((target / "releases").glob("install-*"))
            return subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-p", project,
                "-f", str(work / "compose.json"), *arguments], env=environment,
                capture_output=True, text=True, timeout=180)

        def sql(target, project, query):
            result = compose(target, project, "exec", "-T", "db", "psql", "-U", "postgres", "-d", "caf", "-Atc", query)
            assert result.returncode == 0, result.stderr[-1000:]
            return result.stdout.strip()

        def install(target, project, source):
            target.mkdir()
            projects.append((target, project))
            command = ["sh", str(root / "deploy/caf-host"), "install", str(bundle),
                "--backup", str(source), "--env-file", str(config), "--root", str(target),
                "--project", project, "--port", "0"]
            command.append("--allow-candidate")
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=900)
            return command, result

        try:
            target, project = base / "success", "caf-install-" + uuid4().hex[:10]
            command, result = install(target, project, snapshot)
            if result.returncode:
                logs = list((target / "releases").glob("install-*/install.log"))
                detail = logs[0].read_text()[-6000:] if logs else result.stderr
                for value in values.values():
                    detail = detail.replace(value, "[REDACTED]")
                raise RuntimeError(f"Synthetic installation failed: {detail}")
            receipt = json.loads((target / "installation.json").read_text())
            assert receipt["phase"] == "active" and receipt["application"]["commit"] == manifest.commit
            assert receipt["backup_manifest_sha256"] == checksum(snapshot / "manifest.json")
            status = subprocess.run(["sh", str(root / "deploy/caf-host"), "status", "--root", str(target)],
                                    env=environment, capture_output=True, text=True, timeout=30)
            assert status.returncode == 0 and json.loads(status.stdout)["status"] == "ready"
            secret = compose(target, project, "exec", "-T", "web", "python", "-c",
                             "import os; assert os.environ['OIDC_CLIENT_SECRET'] == 'synthetic$literal-secret'")
            assert secret.returncode == 0
            for table, digest in captured.tables.items():
                if table.startswith("app.") and table not in {"app.auth_session", "app.login_transaction"}:
                    assert int(sql(target, project, f"SELECT count(*) FROM {table}")) == digest.count
            assert sql(target, project, "SELECT count(*) FROM app.auth_session") == "0"
            assert sql(target, project, "SELECT count(*) FROM app.login_transaction") == "0"
            assert sql(target, project, "SELECT count(*) FROM app.invitation WHERE consumed_at IS NULL AND revoked_at IS NULL") == "0"
            assert compose(target, project, "restart", "db", "web", "worker").returncode == 0
            assert compose(target, project, "up", "-d", "--wait", "--wait-timeout", "120", "db", "web", "worker").returncode == 0
            repeated = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30)
            assert repeated.returncode != 0 and "receipt exists" in repeated.stderr
            guard = base / "guard"
            (guard / "data").mkdir(parents=True)
            (guard / "data/preserved").write_text("preserve existing data")
            guarded_command = command.copy()
            guarded_command[guarded_command.index("--root") + 1] = str(guard)
            refused = subprocess.run(guarded_command, env=environment, capture_output=True, text=True, timeout=30)
            assert refused.returncode != 0 and (guard / "data/preserved").read_text() == "preserve existing data"
            assert not (guard / "releases").exists()
            locked = base / "locked"
            locked.mkdir()
            guarded_command[guarded_command.index("--root") + 1] = str(locked)
            with (locked / ".deployment.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                refused = subprocess.run(guarded_command, env=environment, capture_output=True, text=True, timeout=30)
                assert refused.returncode != 0 and "deployment lock" in refused.stderr
            typer.echo("PASS: real snapshot install, account/personal record preservation, credential revocation, readiness, restart, repeat-install refusal")
            typer.echo("PASS: nonempty storage preservation and overlapping-operation lock")

            broken = base / "broken-source"
            shutil.copytree(snapshot, broken)
            (broken / captured.dump_file).write_bytes(b"invalid PostgreSQL archive")
            data = json.loads((broken / "manifest.json").read_text())
            data["dump_sha256"] = checksum(broken / captured.dump_file)
            (broken / "manifest.json").write_text(json.dumps(data))
            failed, failed_project = base / "failed", "caf-install-" + uuid4().hex[:10]
            _, failure = install(failed, failed_project, broken)
            assert failure.returncode != 0
            record = json.loads(next((failed / "releases").glob("install-*/failure.json")).read_text())
            assert record["phase"] == "restore_database"
            running = compose(failed, failed_project, "ps", "--services", "--status", "running")
            assert running.returncode == 0 and set(running.stdout.split()) <= {"db"}
            assert (failed / "installation.json").is_file()
            typer.echo("PASS: failed restore preserves recovery state and never starts serving containers")
        finally:
            for target, project in projects:
                files = list((target / "releases").glob("install-*/compose.json"))
                if files:
                    cleanup = compose(target, project, "down", "--volumes", "--remove-orphans")
                    if cleanup.returncode:
                        raise RuntimeError(f"Owned install cleanup failed for {project}")
                # CI-only cleanup of these newly created, owned test directories.
                # The real installer never removes persistent data on failure.
                subprocess.run(["sudo", "-n", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(target)],
                               env=environment, check=True, capture_output=True)


if __name__ == "__main__":
    app()
