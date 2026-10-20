"""Exercise production service wiring in a disposable, uniquely named Compose project."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from uuid import uuid4

import typer

from verify_production_compose import PASSWORDS, ROOT, fixture, render

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def verify(image: str = typer.Option(...), report: Path = Path("/tmp/caf-stack-integration.json"),
           backup_output: Path | None = None) -> None:
    """Use only synthetic data and owned Docker volumes; never use host data binds."""
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    metadata = json.loads(subprocess.check_output(["docker", "image", "inspect", image], env=environment))[0]
    revision = metadata["Config"]["Labels"]["org.opencontainers.image.revision"]
    assert len(revision) == 40, "Use an image built from an exact committed source revision"
    project = "caf-integration-" + uuid4().hex[:10]
    assert not subprocess.check_output(["docker", "ps", "-aq", "--filter",
                                       f"label=com.docker.compose.project={project}"], env=environment).strip()
    values = fixture()
    values.update({f"PG_{role}_PASSWORD": secrets.token_hex(32) for role in PASSWORDS})
    values.update(CAF_IMAGE=image, CAF_REVISION=revision,
                  CAF_PLATFORM=f"{metadata['Os']}/{metadata['Architecture']}",
                  AUTH_PUBLIC_BASE_URL="https://caf-integration.invalid", OIDC_ISSUER="https://oidc.invalid/")
    parsed = render(values, tools=True)
    assert parsed.returncode == 0, "Production configuration did not render"
    configuration = json.loads(parsed.stdout)
    configuration["name"] = project
    for name, network in configuration["networks"].items():
        network["name"] = f"{project}_{name}"
    configuration["volumes"] = {name: {"name": f"{project}_{name}",
        "labels": {"caf.integration": project}} for name in ("data", "backups", "postgres")}
    hashes = {name: hashlib.sha256((ROOT / f"config/{name}.toml").read_bytes()).hexdigest()
              for name in ("scoring", "depth", "sources", "models")}
    tokens = {str(account): secrets.token_hex(32) for account in (101, 102, 103)}
    secrets_to_redact = [values[f"PG_{role}_PASSWORD"] for role in PASSWORDS] + list(tokens.values())
    secrets_to_redact.append(values["OIDC_CLIENT_SECRET"])
    hosts = {"/srv/caf/data": "data", "/srv/caf/backups": "backups", "/srv/caf/postgres": "postgres"}
    for name, service in configuration["services"].items():
        service["labels"] = {"caf.integration": project}
        service["volumes"] = [{"type": "volume", "source": hosts[mount["source"]],
                               "target": mount["target"]} for mount in service["volumes"]]
        if name == "db":
            continue
        service["environment"].update(CAF_INTEGRATION="owned-synthetic-stack",
                                      CAF_INTEGRATION_CONFIG_HASHES=json.dumps(hashes))
        if name in {"web", "admin"}:
            service["environment"]["CAF_INTEGRATION_TOKENS"] = json.dumps(tokens)
    configuration["services"]["web"]["ports"][0]["published"] = "0"
    probe_source = (ROOT / "scripts/production_stack_probe.py").read_text()
    steps = []
    receipt = {"created_at": datetime.now(timezone.utc).isoformat(), "project": project,
        "application_revision": revision, "image_id": metadata["Id"],
        "architecture": metadata["Architecture"], "runtime_config_sha256": hashes,
        "steps": steps, "passed": False, "cleanup_succeeded": False,
        "limitations": ["Synthetic sessions bypass real Auth0 sign-in; invalid provider domain and no model keys",
            "Production egress network retained; probes invoke no provider requests",
            "Docker volumes replace production host bind paths", "Published port uses a random loopback port",
            "Expired worker lease is injected to simulate interrupted work",
            "Native local architecture; not Ubuntu amd64 acceptance", "Host HTTP and Tailscale HTTPS not tested",
            "No backup/restore drill"]}
    with tempfile.TemporaryDirectory(prefix="caf-stack-") as directory:
        path = Path(directory) / "compose.json"
        path.write_text(json.dumps(configuration))
        path.chmod(0o600)
        prefix = ["docker", "compose", "--env-file", "/dev/null", "-p", project, "-f", str(path)]

        def command(arguments: list[str], *, source: str | None = None, timeout: int = 120) -> str:
            result = subprocess.run([*prefix, *arguments], env=environment, input=source,
                                    capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                detail = result.stderr + result.stdout
                for secret in secrets_to_redact:
                    detail = detail.replace(secret, "[REDACTED]")
                raise RuntimeError(f"Compose command failed ({' '.join(arguments[:4])}): {detail[-5000:]}")
            return result.stdout

        def probe(service: str, *arguments: str) -> None:
            running = service in {"web", "worker"}
            base = ["exec", "-T", service, "python", "-"] if running else [
                "run", "--rm", "-T", "--no-deps", "--entrypoint", "python", service, "-"]
            output = command([*base, *arguments], source=probe_source)
            steps.extend(line for line in output.splitlines() if line.startswith("PASS:"))
            typer.echo(output.strip())

        try:
            command(["up", "-d", "--wait", "--wait-timeout", "90", "db"], timeout=240)
            # Initialize only these new, labelled test volumes. Serving containers keep no capabilities.
            command(["run", "--rm", "--no-deps", "--user", "0:0", "--cap-add", "CHOWN",
                     "--entrypoint", "sh", "admin", "-ec",
                     "mkdir -p /srv/caf/data/blobs; chown 10001:10001 /srv/caf/data /srv/caf/data/blobs /srv/caf/data/backups"])
            command(["run", "--rm", "admin", "db", "migrate"])
            command(["run", "--rm", "admin", "db", "grants"])
            probe("admin", "admin")
            probe("admin", "seed")
            command(["up", "-d", "--wait", "--wait-timeout", "90", "web", "worker"])
            for name in ("db", "web", "worker"):
                identifier = command(["ps", "-q", name]).strip()
                details = json.loads(subprocess.check_output(["docker", "inspect", identifier], env=environment))[0]
                assert details["Config"]["Labels"]["caf.integration"] == project
                assert details["State"]["Running"]
                if name == "db":
                    assert not details["HostConfig"]["PortBindings"]
                    receipt["postgres_image_id"] = details["Image"]
                else:
                    assert details["Config"]["User"] == "10001:10001"
                    assert details["HostConfig"]["ReadonlyRootfs"] is True
                    assert details["HostConfig"]["CapDrop"] == ["ALL"]
                if name == "web":
                    binding = details["NetworkSettings"]["Ports"]["8788/tcp"]
                    assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
            steps.append("PASS: runtime ports, ownership, read-only filesystems and dropped capabilities")
            probe("web", "web", "--update")
            probe("worker", "restricted", "operations")
            probe("pipeline", "restricted", "pipeline")
            probe("admin", "enqueue")
            probe("admin", "completed")
            command(["stop", "worker"])
            probe("admin", "enqueue", "--expired")
            command(["up", "-d", "worker"])
            probe("admin", "completed", "--reclaimed")
            command(["stop", "web", "worker", "db"])
            command(["up", "-d", "--wait", "--wait-timeout", "90", "web", "worker"])
            probe("web", "web")
            probe("admin", "durable")
            command(["up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90", "web", "worker"])
            probe("web", "web")
            probe("admin", "durable")
            if backup_output is not None:
                capture = ("from pathlib import Path; from caf_common.backup import create_backup; "
                           "Path('/srv/caf/data/blobs/install-fixture.pdf').write_bytes(b'owned synthetic source'); "
                           "print(create_backup().backup_dir)")
                captured = command(["exec", "-T", "web", "python", "-c", capture]).strip()
                container = command(["ps", "-q", "web"]).strip()
                backup_output.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["docker", "cp", f"{container}:{captured}", str(backup_output)],
                               env=environment, check=True)
            receipt["passed"] = True
        finally:
            cleanup = subprocess.run([*prefix, "down", "--volumes", "--remove-orphans"],
                                     env=environment, capture_output=True, text=True, timeout=120)
            receipt["cleanup_succeeded"] = cleanup.returncode == 0
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(receipt, indent=2) + "\n")
            if cleanup.returncode:
                raise RuntimeError(f"Cleanup failed for owned project {project}; see Docker state")
    typer.echo(f"PASS: isolated production stack; receipt: {report}")


if __name__ == "__main__":
    app()
