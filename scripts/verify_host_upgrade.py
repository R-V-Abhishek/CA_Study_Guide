"""Exercise upgrade, scheduled backup and the health watch against a real disposable installation."""

from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from uuid import uuid4

import typer

from caf_cli.host_bundle import (
    PAYLOAD,
    FileRecord,
    ImageRecord,
    check_manifest,
    digest,
    verify_archive,
)
from caf_common.recovery_manifest import inspect_recovery_files
from verify_production_compose import fixture

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic$literal-secret"
# What migration 0010 adds; the drill removes it to recreate a host still on the previous schema.
PREVIOUS_SCHEMA = "0009_question_language"
REVERT_0010 = [
    "ALTER TABLE app.note DROP CONSTRAINT check_note_body_length",
    "ALTER TABLE app.mock_test DROP CONSTRAINT check_mock_test_label_length",
    "ALTER TABLE app.mock_test DROP CONSTRAINT check_mock_test_notes_length",
    "DROP INDEX app.ix_revision_event_user_node_at",
    "DROP INDEX app.ix_mock_test_user_taken_on",
    "DROP INDEX app.ix_study_session_user_id",
    f"UPDATE ops.alembic_version SET version_num = '{PREVIOUS_SCHEMA}'",
]
BREAK_STARTUP = (
    "RUN f=$(python -c 'import caf_api; print(caf_api.__file__)') "
    '&& echo "raise RuntimeError(\'drill: deliberately broken release\')" >> "$(dirname "$f")/main.py"'
)


def derive(
    source: Path, directory: Path, version: str, *, broken: bool = False
) -> tuple[Path, str]:
    """Repack an existing bundle as a newer release: same layers, new version labels.

    The result is a real verified bundle with a loadable image, so upgrade exercises its normal
    verification, loading and activation. A broken release fails at application import.
    """
    manifest = verify_archive(source)
    commit = hashlib.sha1(version.encode()).hexdigest()
    architecture = manifest.platform.split("/")[1]
    reference = f"caf:{version}-candidate-{commit[:12]}-{architecture}"
    lines = [
        f"FROM {manifest.application.reference}",
        f"LABEL org.opencontainers.image.version={version} org.opencontainers.image.revision={commit}",
    ]
    if broken:
        lines += ["USER root", BREAK_STARTUP, "USER 10001:10001"]
    subprocess.run(
        ["docker", "build", "--pull=false", "-q", "-t", reference, "-"],
        input="\n".join(lines) + "\n",
        text=True,
        check=True,
        capture_output=True,
    )
    directory.mkdir()
    with tarfile.open(source, "r:gz") as archive:
        archive.extractall(directory, filter="data")
    subprocess.run(
        [
            "docker",
            "save",
            "-o",
            str(directory / "images.tar"),
            reference,
            manifest.postgres.reference,
        ],
        check=True,
    )
    image_id = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", reference], check=True, capture_output=True, text=True
        ).stdout
    )[0]["Id"]
    files = {
        **manifest.files,
        "images.tar": FileRecord(
            sha256=digest(directory / "images.tar"), size=(directory / "images.tar").stat().st_size
        ),
    }
    derived = manifest.model_copy(
        update={
            "version": version,
            "commit": commit,
            "created_at": datetime.now(timezone.utc),
            "application": ImageRecord(reference=reference, image_id=image_id),
            "files": files,
        }
    )
    check_manifest(derived)
    (directory / "manifest.json").write_text(derived.model_dump_json(indent=2) + "\n")
    names = PAYLOAD | {"manifest.json"}
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest(directory / name)}  {name}\n" for name in sorted(names))
    )
    bundle = directory.parent / f"caf-{version}-candidate-{commit[:12]}-{architecture}.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name in sorted(names | {"SHA256SUMS"}):
            archive.add(directory / name, arcname=name, recursive=False)
    bundle.with_name(bundle.name + ".sha256").write_text(f"{digest(bundle)}  {bundle.name}\n")
    verify_archive(bundle)
    return bundle, reference


class Receiver(BaseHTTPRequestHandler):
    """Stands in for the notification service and keeps every message it is sent."""

    messages: list[str] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.messages.append(self.rfile.read(length).decode())
        self.send_response(200)
        self.end_headers()

    def log_message(self, *arguments):
        pass


@app.command()
def verify(bundle: Path, snapshot: Path, image: str) -> None:
    if sys.platform != "linux":
        typer.echo("SKIP: host upgrade is exercised on native Linux CI")
        return
    manifest = verify_archive(bundle)
    captured = inspect_recovery_files(snapshot)
    tables = [
        table
        for table in captured.tables
        if table.startswith("app.") and table not in {"app.auth_session", "app.login_transaction"}
    ]
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    environment["CAF_HOST_IMAGE"] = image
    projects = []
    with tempfile.TemporaryDirectory(prefix="caf-owned-upgrade-") as temporary:
        base = Path(temporary)
        config = base / "compose.env"
        values = fixture()
        values.update(OIDC_CLIENT_SECRET=SECRET)
        config.write_text("".join(f"{key}='{value}'\n" for key, value in values.items()))
        config.chmod(0o600)
        target = base / "root"
        target.mkdir()
        project = "caf-install-" + uuid4().hex[:10]
        projects.append((target, project))

        def redact(text):
            for value in values.values():
                text = text.replace(value, "[REDACTED]")
            return text

        def host(*arguments, tooling=image, timeout=900):
            return subprocess.run(
                ["sh", str(ROOT / "deploy/caf-host"), *arguments],
                env={**environment, "CAF_HOST_IMAGE": tooling},
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        def compose(*arguments):
            return subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    "/dev/null",
                    "-p",
                    project,
                    "-f",
                    str(target / "current-compose.json"),
                    *arguments,
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=300,
            )

        def sql(query):
            result = compose(
                "exec", "-T", "db", "psql", "-U", "postgres", "-d", "caf", "-Atc", query
            )
            assert result.returncode == 0, result.stderr[-1000:]
            return result.stdout.strip()

        def counts():
            return {table: int(sql(f"SELECT count(*) FROM {table}")) for table in tables}

        def app_run(directory, *command):
            """Run a read-only command on a directory owned by the application UID, as the application."""
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--user",
                    "10001:10001",
                    "--mount",
                    f"type=bind,source={target / directory},target=/listing,readonly",
                    "--entrypoint",
                    command[0],
                    image,
                    *command[1:],
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            return result.stdout

        def app_files(directory):
            return app_run(directory, "ls", "-1", "/listing").split()

        def app_status():
            return json.loads(app_run("backups", "cat", "/listing/status.json"))

        def receipt():
            return json.loads((target / "installation.json").read_text())

        def expect_ready(version):
            status = host("status", "--root", str(target), timeout=60)
            report = json.loads(status.stdout)
            assert status.returncode == 0 and report["status"] == "ready", status.stdout
            assert report["application"] == version, report

        def failure_detail(result, pattern):
            logs = sorted(target.glob(pattern))
            detail = logs[-1].read_text()[-6000:] if logs else result.stderr
            return redact(result.stderr[-1500:] + "\n" + detail)

        def upgrade(release, reference, *extra, timeout=900):
            return host(
                "upgrade",
                str(release),
                "--env-file",
                str(config),
                "--root",
                str(target),
                "--allow-candidate",
                *extra,
                tooling=reference,
                timeout=timeout,
            )

        try:
            installed = host(
                "install",
                str(bundle),
                "--backup",
                str(snapshot),
                "--env-file",
                str(config),
                "--root",
                str(target),
                "--project",
                project,
                "--port",
                "0",
                "--allow-candidate",
            )
            if installed.returncode:
                raise RuntimeError(
                    "Synthetic installation failed: "
                    + failure_detail(installed, "releases/install-*/install.log")
                )
            expect_ready(manifest.version)
            for statement in REVERT_0010:
                sql(statement)
            before = counts()
            assert all(before[table] == captured.tables[table].count for table in tables)
            assert sql("SELECT version_num FROM ops.alembic_version") == PREVIOUS_SCHEMA
            typer.echo(
                "PASS: installed release, then recreated a host still on the previous schema"
            )

            # 1. A forward upgrade that applies a real migration.
            work = base / "bundles"
            work.mkdir()
            second, second_image = derive(bundle, work / "v0.2.2", "v0.2.2")
            upgraded = upgrade(second, second_image)
            if upgraded.returncode:
                raise RuntimeError(
                    "Upgrade failed: " + failure_detail(upgraded, "releases/upgrade-*/upgrade.log")
                )
            current = receipt()
            assert current["application"]["version"] == "v0.2.2"
            assert current["previous"][0]["application"]["version"] == manifest.version
            snapshot_name = current["previous"][0]["snapshot"]["name"]
            assert snapshot_name.startswith("caf_"), snapshot_name
            assert snapshot_name in app_files("backups"), "the receipt must name a real snapshot"
            assert not (target / ".upgrade-in-progress").exists()
            assert (target / "releases" / bundle.name).is_file()  # the previous bundle is retained
            expect_ready("v0.2.2")
            assert counts() == before, "personal and shared records must survive the upgrade"
            assert sql("SELECT version_num FROM ops.alembic_version") == manifest.required_schema
            assert (
                sql(
                    "SELECT count(*) FROM pg_constraint WHERE conname IN "
                    "('check_note_body_length','check_mock_test_label_length','check_mock_test_notes_length')"
                )
                == "3"
            )
            assert (
                sql(
                    "SELECT count(*) FROM pg_indexes WHERE indexname IN "
                    "('ix_revision_event_user_node_at','ix_mock_test_user_taken_on','ix_study_session_user_id')"
                )
                == "3"
            )
            typer.echo(
                "PASS: upgrade with a real migration kept every record, the previous release and its snapshot"
            )

            # 2. Refusals that must leave the running release alone.
            for refused, name in ((upgrade(second, second_image), "the same version"),):
                assert refused.returncode != 0, f"upgrade to {name} must be refused"
            with (target / ".deployment.lock").open("w") as lock:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = upgrade(second, second_image, timeout=60)
                assert locked.returncode != 0 and "deployment lock" in locked.stderr
            expect_ready("v0.2.2")
            typer.echo(
                "PASS: same-version and overlapping upgrades are refused without disturbance"
            )

            # 3. Scheduled snapshot, unencrypted then encrypted to a public recipient.
            absent = base / "no-recipient.txt"
            plain = host(
                "backup", "--root", str(target), "--recipient", str(absent), tooling=second_image
            )
            assert plain.returncode == 0, redact(plain.stderr[-1500:])
            status = app_status()
            assert status["state"] == "ok" and status["encryption"] == "not_configured", status
            if shutil.which("age") and shutil.which("age-keygen"):
                identity = base / "identity.txt"
                subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
                recipient = base / "recipient.txt"
                recipient.write_text(
                    subprocess.run(
                        ["age-keygen", "-y", str(identity)],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout
                )
                sealed = host(
                    "backup",
                    "--root",
                    str(target),
                    "--recipient",
                    str(recipient),
                    tooling=second_image,
                )
                assert sealed.returncode == 0, redact(sealed.stderr[-1500:])
                status = app_status()
                assert status["encryption"] == "encrypted", status
                encrypted = (
                    target / "encrypted-backups" / f"{status['snapshot']['name']}.tar.gz.age"
                )
                assert encrypted.is_file()
                listing = subprocess.run(
                    f"age -d -i {identity} {encrypted} | tar -tz",
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                assert f"{status['snapshot']['name']}/manifest.json" in listing
                typer.echo("PASS: scheduled snapshot, encryption and an authenticated decryption")
            else:
                typer.echo("SKIP: age is not installed, so encryption was not exercised")

            # 4. Health watch: one alert per problem, silence while it lasts, one recovery message.
            receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
            Receiver.messages = []
            threading.Thread(target=receiver.serve_forever, daemon=True).start()
            settings = base / "watch.env"
            settings.write_text(
                f"CAF_WATCH_WEBHOOK_URL=http://127.0.0.1:{receiver.server_port}/topic\n"
            )
            settings.chmod(0o600)
            deadline = time.monotonic() + 120
            while (
                "worker-heartbeat.json" not in app_files("backups") and time.monotonic() < deadline
            ):
                time.sleep(2)
            assert "worker-heartbeat.json" in app_files("backups"), (
                "the worker never wrote its heartbeat"
            )

            def watch():
                result = host(
                    "watch",
                    "--root",
                    str(target),
                    "--settings",
                    str(settings),
                    tooling=second_image,
                )
                assert result.returncode == 0, redact(result.stderr[-1500:])
                return result

            watch()
            assert Receiver.messages == [], "a healthy deployment sends nothing"
            assert compose("stop", "web").returncode == 0
            watch()
            watch()
            assert len(Receiver.messages) == 1 and "NOT_READY" in Receiver.messages[0], (
                Receiver.messages
            )
            assert compose("up", "-d", "--wait", "--wait-timeout", "120", "web").returncode == 0
            watch()
            assert len(Receiver.messages) == 2 and "RECOVERED" in Receiver.messages[1], (
                Receiver.messages
            )
            receiver.shutdown()
            typer.echo(
                "PASS: watch alerts once, stays quiet while the problem lasts, then reports recovery"
            )

            # 5. A release that cannot start must roll back to the one that was serving.
            before_failure = counts()
            third, third_image = derive(bundle, work / "v0.2.3", "v0.2.3", broken=True)
            failed = upgrade(third, third_image, timeout=900)
            assert failed.returncode != 0, "a release that cannot start must fail the upgrade"
            assert receipt()["application"]["version"] == "v0.2.2"
            assert not (target / ".upgrade-in-progress").exists()
            records = sorted(target.glob("releases/upgrade-*/failure.json"))
            assert records and json.loads(records[-1].read_text())["database_migrated"] is False
            expect_ready("v0.2.2")
            assert counts() == before_failure
            typer.echo(
                "PASS: a release that cannot start was rolled back with the database untouched"
            )

            # 6. After that failure a good newer release upgrades normally with no migration needed.
            fourth, fourth_image = derive(bundle, work / "v0.2.4", "v0.2.4")
            again = upgrade(fourth, fourth_image)
            if again.returncode:
                raise RuntimeError(
                    "Same-schema upgrade failed: "
                    + failure_detail(again, "releases/upgrade-*/upgrade.log")
                )
            current = receipt()
            assert current["application"]["version"] == "v0.2.4" and len(current["previous"]) == 2
            expect_ready("v0.2.4")
            assert counts() == before_failure
            typer.echo(
                "PASS: same-schema upgrade after a rolled-back attempt, two previous releases retained"
            )
        finally:
            for destination, name in projects:
                pointer = destination / "current-compose.json"
                if pointer.exists():
                    cleanup = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            "/dev/null",
                            "-p",
                            name,
                            "-f",
                            str(pointer),
                            "down",
                            "--volumes",
                            "--remove-orphans",
                        ],
                        env=environment,
                        capture_output=True,
                        timeout=180,
                    )
                    if cleanup.returncode:
                        raise RuntimeError(f"Owned upgrade cleanup failed for {name}")
                # CI-only cleanup of this newly created, owned test directory; the real tooling
                # never removes persistent data.
                subprocess.run(
                    ["sudo", "-n", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(destination)],
                    env=environment,
                    check=True,
                    capture_output=True,
                )


if __name__ == "__main__":
    app()
