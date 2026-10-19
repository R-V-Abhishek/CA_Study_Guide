"""Validate real Compose output with disposable configuration, without a daemon."""

import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import typer

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
ROOT = Path(__file__).resolve().parents[1]
PASSWORDS = ("SUPERUSER", "APP", "IDENTITY", "CURATOR", "OPERATIONS", "PIPELINE", "BACKUP")


def fixture() -> dict[str, str]:
    values = {f"PG_{role}_PASSWORD": f"{index + 1:064x}" for index, role in enumerate(PASSWORDS)}
    return {**values, "CAF_IMAGE": "caf:configuration-test", "CAF_REVISION": "a" * 40,
            "AUTH_PUBLIC_BASE_URL": "https://caf-home.example.ts.net",
            "OIDC_ISSUER": "https://example.auth0.com/", "OIDC_CLIENT_ID": "fixture-client",
            "OIDC_CLIENT_SECRET": "fixture-secret"}


def render(values: dict[str, str], *, tools: bool = False) -> subprocess.CompletedProcess[str]:
    # Do not load the user's .env or inherit actual application credentials.
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    environment.update(values)
    command = ["docker", "compose", "--env-file", "/dev/null", "-f", str(ROOT / "compose.production.yml")]
    if tools:
        command.extend(["--profile", "tools"])
    return subprocess.run([*command, "config", "--format", "json"], cwd=ROOT,
                          env=environment, capture_output=True, text=True, timeout=30)


@app.command()
def verify() -> None:
    """Check production wiring and failure cases using only dummy credentials."""
    values = fixture()
    normal = render(values)
    assert normal.returncode == 0, "Default Compose configuration did not render"
    assert set(json.loads(normal.stdout)["services"]) == {"db", "web", "worker"}
    result = render(values, tools=True)
    assert result.returncode == 0, "Compose tools configuration did not render"
    configuration = json.loads(result.stdout)
    services = configuration["services"]
    assert set(services) == {"db", "web", "worker", "admin", "pipeline"}
    assert configuration["networks"]["backend"]["internal"] is True
    assert not configuration["networks"]["egress"].get("internal", False)
    assert set(services["db"]["networks"]) == {"backend"}
    assert set(services["worker"]["networks"]) == {"backend"}
    assert set(services["web"]["networks"]) == {"backend", "egress"}
    assert services["db"]["image"].startswith("postgres:16-")
    assert services["db"]["environment"]["POSTGRES_PASSWORD"] == values["PG_SUPERUSER_PASSWORD"]
    port = services["web"]["ports"]
    assert len(port) == 1
    assert (port[0]["host_ip"], port[0]["published"], port[0]["target"]) == ("127.0.0.1", "8788", 8788)
    for name, service in services.items():
        assert "build" not in service and not service.get("privileged", False)
        assert service["cpus"] > 0 and int(service["mem_limit"]) > 0
        assert service["logging"]["options"] == {"max-file": "3", "max-size": "10m"}
        if name != "web":
            assert not service.get("ports")
        for mount in service["volumes"]:
            assert mount["source"] in {"/srv/caf/data", "/srv/caf/postgres", "/srv/caf/backups"}
            # Compose v2 omits false booleans in canonical JSON; v5 retains them.
            assert mount["bind"].get("create_host_path", False) is False
        if name == "db":
            assert service["restart"] == "unless-stopped"
            continue
        assert service["image"] == values["CAF_IMAGE"]
        assert service["pull_policy"] == "never"
        assert service["user"] == "10001:10001" and service["read_only"] is True
        mounts = {mount["source"]: mount["target"] for mount in service["volumes"]}
        assert mounts == {"/srv/caf/data": "/srv/caf/data", "/srv/caf/backups": "/srv/caf/data/backups"}
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        environment = service["environment"]
        assert environment["CAF_ENV"] == "production" and environment["AUTH_LOCAL_DEVELOPMENT"] == "false"
        assert environment["GEMINI_API_KEY"] == environment["OPENROUTER_API_KEY"] == ""
        if name in {"web", "worker", "pipeline"}:
            assert "MIGRATION_DATABASE_URL" not in environment
            assert "PG_SUPERUSER_PASSWORD" not in environment
            assert values["PG_SUPERUSER_PASSWORD"] not in json.dumps(environment)
        if name in {"admin", "pipeline"}:
            assert service["profiles"] == ["tools"] and service["restart"] == "no"
            assert service["entrypoint"] == ["caf"] and service["command"] == ["--help"]
        else:
            assert service["restart"] == "unless-stopped"
    web = services["web"]["environment"]
    for role, variable in (("APP", "STUDENT"), ("IDENTITY", "IDENTITY"), ("CURATOR", "CURATION"),
                           ("OPERATIONS", "OPERATIONS"), ("BACKUP", "BACKUP")):
        url = urlsplit(web[f"{variable}_DATABASE_URL"])
        assert url.username == f"caf_{role.lower()}" and url.password == values[f"PG_{role}_PASSWORD"]
        assert (url.hostname, url.port, url.path) == ("db", 5432, "/caf")
    assert web["OIDC_REDIRECT_URI"] == values["AUTH_PUBLIC_BASE_URL"] + "/auth/callback"
    worker = services["worker"]["environment"]
    assert {key for key in worker if key.endswith("DATABASE_URL")} == {"OPERATIONS_DATABASE_URL"}
    assert not any(key.startswith("OIDC_") for key in worker)
    pipeline = services["pipeline"]["environment"]
    assert urlsplit(pipeline["DATABASE_URL"]).username == "caf_pipeline"
    admin = services["admin"]["environment"]
    assert admin["DATABASE_URL"] == admin["MIGRATION_DATABASE_URL"]
    for role in PASSWORDS[1:]:
        assert admin[f"PG_{role}_PASSWORD"] == values[f"PG_{role}_PASSWORD"]
    for name in values:
        missing = render({**values, name: ""}, tools=True)
        assert missing.returncode != 0, f"Missing {name} was accepted"
    typer.echo(f"PASS: service isolation, loopback port, role wiring, limits, manual tools, and {len(values)} required-value failures")


if __name__ == "__main__":
    app()
