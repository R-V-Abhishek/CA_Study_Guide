"""Read-only host inspection and offline bundle verification; no Docker administration."""

from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import tarfile
from typing import Literal

from pydantic import BaseModel, Field
import typer

from caf_cli.host_bundle import verify_archive

app = typer.Typer(help="Packaged home-host inspection tools", add_completion=False,
                  pretty_exceptions_enable=False)
GIB = 1024**3


class Finding(BaseModel):
    code: str
    level: Literal["warning", "blocker"]
    message: str


class HostReport(BaseModel):
    format_version: Literal[1] = 1
    collected_at: datetime
    tool_image: str | None
    os_id: str
    os_version: str
    platform: str
    cpu_threads: int = Field(ge=1)
    ram_total_bytes: int = Field(ge=1)
    ram_available_bytes: int = Field(ge=0)
    free_storage_bytes: int = Field(ge=0)
    docker_version: str | None
    compose_version: str | None
    tailscale_state: str
    tailscale_online: bool | None
    external_backup_mounted: bool
    findings: list[Finding]
    observations: dict[str, object]
    unverified: list[str]


def probe(root: Path, name: str) -> tuple[int, str]:
    path = root / f"{name}.out"
    if path.stat().st_size > 2 * 1024**2:
        raise ValueError(f"Collected probe exceeds size limit: {name}")
    return int((root / f"{name}.code").read_text()), path.read_text()


def required(root: Path, name: str) -> str:
    code, value = probe(root, name)
    if code:
        raise ValueError(f"Required host probe failed: {name} (exit {code})")
    return value


def properties(value: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in value.splitlines() if "=" in line)


def inspect_host(root: Path) -> HostReport:
    findings: list[Finding] = []

    def note(code: str, message: str, *, blocker: bool = False) -> None:
        findings.append(Finding(code=code, level="blocker" if blocker else "warning", message=message))

    release = {key: shlex.split(value)[0] for key, value in properties(required(root, "os")).items()
               if key in {"ID", "VERSION_ID"}}
    machine = required(root, "architecture").strip()
    platforms = {"x86_64": "linux/amd64", "aarch64": "linux/arm64"}
    platform = platforms.get(machine, "unsupported")
    if platform == "unsupported":
        note("ARCHITECTURE", "No release platform supports this CPU architecture", blocker=True)
    if release["ID"] != "ubuntu" or release["VERSION_ID"] != "26.04":
        note("OS_VERSION", "Host differs from the selected Ubuntu 26.04 deployment target")
    memory = {key: int(value.split()[0]) * 1024
              for key, value in (line.split(":", 1) for line in required(root, "memory").splitlines())
              if key in {"MemTotal", "MemAvailable"}}
    free = int(required(root, "storage").splitlines()[1].split()[3]) * 1024
    if free < 50 * GIB:
        note("INITIAL_FREE_SPACE", "Initial installation requires at least 50 GiB free", blocker=True)
    if memory["MemTotal"] < 8 * GIB:
        note("LOW_RAM", "Less than 8 GiB RAM; runtime budgets need measurement")

    observations: dict[str, object] = {}
    versions = {}
    for name in ("docker", "compose"):
        code, text = probe(root, name)
        versions[name] = text.strip() if code == 0 else None
        if code:
            note(name.upper(), f"Cannot inspect {name}; command exit {code}", blocker=True)
    code, text = probe(root, "tailscale")
    state, online = "unavailable", None
    if code == 0:
        network = json.loads(text)
        state = network["BackendState"]
        online = None if network["Self"] is None else network["Self"]["Online"]
        # Never expose AuthURL, peer/user records, health errors or device addresses.
    if state != "Running" or online is not True:
        note("TAILSCALE", "Private connectivity is not confirmed", blocker=True)
    code, text = probe(root, "backup_mount")
    mounted = code == 0 and any(item["target"] == "/mnt/caf-backup"
                                for item in json.loads(text)["filesystems"])
    if not mounted:
        note("BACKUP_DRIVE", "External backup drive is not mounted; production import remains gated")
    observations["external_backup_mount"] = json.loads(text)["filesystems"] if mounted else []

    code, text = probe(root, "clock")
    clock = properties(text) if code == 0 else {}
    observations["clock"] = clock
    if clock.get("NTPSynchronized") != "yes":
        note("CLOCK", "Clock synchronization is not confirmed")
    code, text = probe(root, "services")
    services = [properties(block) for block in text.strip().split("\n\n") if block.strip()]
    observations["services"] = services
    if code or len(services) != 3 or any(item.get("ActiveState") != "active" or
            item.get("UnitFileState") != "enabled" for item in services):
        note("BOOT_SERVICES", "Docker, Tailscale and SSH must be active and enabled at boot")
    code, text = probe(root, "firewall")
    observations["firewall"] = text.strip() if code == 0 else "unverified: permission denied or unavailable"
    if code:
        note("FIREWALL_UNVERIFIED", "Firewall requires a separate authorized read; this tool never elevates privileges")
    code, text = probe(root, "suspend")
    suspend = {}
    if code == 0:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", ";", "[")) and "=" in line:
                key, value = line.split("=", 1)
                if key in {"HandleLidSwitch", "HandleLidSwitchExternalPower", "HandleLidSwitchDocked", "IdleAction"}:
                    suspend[key.strip()] = value.strip()
    observations["suspend_policy"] = suspend
    if suspend.get("HandleLidSwitchExternalPower", suspend.get("HandleLidSwitch")) != "ignore":
        note("AC_LID_POLICY", "Ignoring lid closure on AC power is not confirmed")
    code, text = probe(root, "power")
    power: dict[str, dict[str, str]] = {}
    if code == 0:
        for line in text.splitlines():
            device, key, value = line.split(" ", 2)
            power.setdefault(device, {})[key] = value
    observations["power"] = power
    mains = [item for item in power.values() if item["type"] == "Mains"]
    if not mains or not any(item.get("online") == "1" for item in mains):
        note("AC_POWER", "Connection to AC power is not confirmed")
    code, text = probe(root, "temperature")
    temperatures = {key: int(value) / 1000 for key, value in
                    (line.split() for line in text.splitlines())} if code == 0 else {}
    observations["temperature_celsius"] = temperatures
    if not temperatures:
        note("TEMPERATURE_UNAVAILABLE", "No thermal-zone temperature was available")
    elif max(temperatures.values()) >= 85:
        note("HIGH_TEMPERATURE", "A sampled thermal zone is at least 85 C; inspect cooling and workload")
    code, text = probe(root, "users")
    if code:
        note("USERS_UNVERIFIED", "Login and service-account records could not be inspected")
    users = [dict(zip(("name", "uid", "gid", "home", "shell"), line.split(":")))
             for line in text.splitlines()] if code == 0 else []
    observations["login_accounts"] = [item for item in users if 1000 <= int(item["uid"]) < 60000
                                      and item["shell"] not in {"/bin/false", "/usr/sbin/nologin"}]
    observations["greeter_accounts"] = [item for item in users if item["name"] in {"gdm", "gdm-greeter", "Debian-gdm"}]
    for name in ("filesystem", "disks"):
        code, text = probe(root, name)
        observations[name] = json.loads(text) if code == 0 else {"unverified": True}
    for name in ("containers", "listeners", "layout"):
        code, text = probe(root, name)
        observations[name] = text.splitlines() if code == 0 else [f"unverified: probe exit {code}"]
    return HostReport(collected_at=(root / "collected_at").read_text().strip(),
        tool_image=os.environ.get("CAF_HOST_TOOL_IMAGE"), os_id=release["ID"], os_version=release["VERSION_ID"],
        platform=platform, cpu_threads=int(required(root, "cpu")), ram_total_bytes=memory["MemTotal"],
        ram_available_bytes=memory["MemAvailable"], free_storage_bytes=free,
        docker_version=versions["docker"], compose_version=versions["compose"],
        tailscale_state=state, tailscale_online=online, external_backup_mounted=mounted,
        findings=findings, observations=observations,
        unverified=["Privileged SMART/disk health", "Measured internet upload/download",
            "Reboot, Wi-Fi recovery and disk-unlock behavior", "Encrypted backup write/read and isolated restore",
            "Separate student-device HTTPS and Auth0 access", "Low-battery shutdown and charge-limit behavior"])


@app.command()
def preflight(inspection: Path = typer.Option(..., help="Private snapshot made by collect-host.sh")) -> None:
    """Emit a non-secret report; exit 2 means findings require attention."""
    try:
        report = inspect_host(inspection)
    except (OSError, ValueError, KeyError, IndexError) as error:
        typer.echo(f"Preflight failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(report.model_dump_json(indent=2))
    if report.findings:
        raise typer.Exit(2)


@app.command()
def verify_bundle(bundle: Path, platform: str = typer.Option(...), allow_candidate: bool = False) -> None:
    """Verify an offline bundle without extracting, loading images or starting services."""
    try:
        manifest = verify_archive(bundle)
        if manifest.platform != platform:
            raise ValueError("Bundle architecture differs from the selected host")
        if manifest.candidate and not allow_candidate:
            raise ValueError("Candidate bundle is not a production release")
    except (OSError, ValueError, tarfile.TarError) as error:
        typer.echo(f"Bundle verification failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(manifest.model_dump_json(indent=2))
