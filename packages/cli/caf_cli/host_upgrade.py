"""Packaged upgrade planning and snapshot validation; Docker stays on the host."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re

import typer

from caf_cli.host_bundle import digest, verify_archive
from caf_cli.host_install import effective_compose
from caf_common.recovery_manifest import checksum, inspect_recovery_files

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


def version_key(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"Invalid release version: {version}")
    return int(match[1]), int(match[2]), int(match[3])


def migration_chain(head: str) -> list[str]:
    """Revisions from the first migration up to head, read from this image's own scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    if script.get_current_head() != head:
        raise ValueError("Release manifest schema differs from the packaged migration head")
    return [revision.revision for revision in script.walk_revisions(base="base", head=head)]


def plan_upgrade(
    bundle: Path,
    installation: dict,
    rendered: Path,
    output: Path,
    *,
    installed_schema: str,
    port: int,
    allow_candidate: bool = False,
) -> dict:
    """Validate an upgrade without touching Docker, storage or the database."""
    if installation.get("phase") != "active":
        raise ValueError("Upgrade requires an active installation receipt")
    manifest = verify_archive(bundle)
    current = installation["application"]
    if manifest.candidate and not allow_candidate:
        raise ValueError("Candidate upgrade requires explicit --allow-candidate")
    if manifest.platform != current["platform"]:
        raise ValueError("Upgrade bundle architecture differs from the installed release")
    if manifest.postgres.image_id != current["postgres"]["image_id"]:
        raise ValueError("PostgreSQL image changes are not part of an application upgrade")
    # A candidate may be replaced by the final build of the same version, never the reverse.
    finalizes_candidate = current["candidate"] and not manifest.candidate
    if version_key(manifest.version) < version_key(current["version"]) or (
        version_key(manifest.version) == version_key(current["version"]) and not finalizes_candidate
    ):
        raise ValueError(
            f"Installed {current['version']} is not older than {manifest.version}; "
            "downgrades and reinstallations are not performed by upgrade"
        )
    chain = migration_chain(manifest.required_schema)
    if installed_schema not in chain:
        raise ValueError(
            "Live database schema is unknown to this release; it may be newer. "
            "Restore or upgrade tooling must be reviewed manually"
        )
    configuration = effective_compose(
        manifest, rendered, installation["destination"], installation["project"], port
    )
    (output / "compose.json").write_text(json.dumps(configuration, indent=2) + "\n")
    receipt = {
        "format_version": 1,
        "phase": "upgrade_prepared",
        "project": installation["project"],
        "destination": installation["destination"],
        "application": manifest.model_dump(mode="json"),
        "bundle_sha256": digest(bundle),
        "database_revision": installed_schema,
        "target_database_revision": manifest.required_schema,
        "migration_required": installed_schema != manifest.required_schema,
        "from_version": current["version"],
        "from_commit": current["commit"],
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


@app.command()
def prepare(
    bundle: Path,
    installation: Path,
    rendered: Path,
    output: Path,
    installed_schema: str = typer.Option(...),
    port: int = 8788,
    allow_candidate: bool = False,
) -> None:
    """Write the effective Compose file and a plan receipt for an upgrade."""
    receipt = plan_upgrade(
        bundle,
        json.loads(installation.read_text()),
        rendered,
        output,
        installed_schema=installed_schema,
        port=port,
        allow_candidate=allow_candidate,
    )
    typer.echo(
        json.dumps(
            {
                "from": receipt["from_version"],
                "to": receipt["application"]["version"],
                "migration_required": receipt["migration_required"],
            }
        )
    )


def verify_snapshot(
    snapshot: Path, *, expected_schema: str, not_before: datetime, name: str | None = None
) -> dict:
    """The snapshot must be intact, complete, pre-migration and taken after services stopped.

    The host script mounts the directory at a fixed path, so it names the real directory itself."""
    from caf_common.backup import critical_tables

    manifest = inspect_recovery_files(snapshot)
    if critical_tables(manifest.database_revision) - manifest.tables.keys():
        raise ValueError("Protected tables missing from snapshot")
    if manifest.database_revision != expected_schema:
        raise ValueError("Snapshot schema differs from the live pre-upgrade schema")
    if manifest.created_at < not_before:
        raise ValueError(
            "Snapshot predates the maintenance window; a stale snapshot cannot protect this upgrade"
        )
    return {
        "name": name or snapshot.name,
        "manifest_sha256": checksum(snapshot / "manifest.json"),
        "created_at": manifest.created_at.isoformat(),
        "database_revision": manifest.database_revision,
        "tables": len(manifest.tables),
        "archived_files": len(manifest.files),
        "file_integrity_verified": True,
        "restore_verified": False,
    }


@app.command("verify-snapshot")
def verify_snapshot_command(
    snapshot: Path,
    expected_schema: str = typer.Option(...),
    not_before: str = typer.Option(..., help="ISO-8601 time services stopped"),
    name: str | None = typer.Option(None, help="Snapshot directory name on the host"),
) -> None:
    moment = datetime.fromisoformat(not_before)
    if moment.tzinfo is None:
        raise ValueError("not_before requires a UTC offset")
    typer.echo(
        json.dumps(
            verify_snapshot(snapshot, expected_schema=expected_schema, not_before=moment, name=name)
        )
    )


def finalize(
    installation: dict,
    upgrade: dict,
    snapshot: dict,
    *,
    schema: str,
    release_directory: str,
    upgraded_at: datetime | None = None,
) -> dict:
    """Merge the upgrade into the installation receipt, retaining the previous release."""
    if upgrade["phase"] != "upgrade_prepared" or "loaded_images" not in upgrade:
        raise ValueError("Upgrade receipt is not a verified, loaded plan")
    if schema != upgrade["target_database_revision"]:
        raise ValueError("Final schema differs from the release's required schema")
    moment = (upgraded_at or datetime.now(timezone.utc)).isoformat()
    previous = {
        "application": installation["application"],
        "release_directory": installation["release_directory"],
        "database_revision": upgrade["database_revision"],
        "loaded_images": installation.get("loaded_images"),
        "snapshot": snapshot,
        "replaced_at": moment,
    }
    result = {
        **installation,
        "application": upgrade["application"],
        "database_revision": schema,
        "release_directory": release_directory,
        "loaded_images": upgrade["loaded_images"],
        "bundle_sha256": upgrade["bundle_sha256"],
        "upgraded_at": moment,
        "previous": [previous, *installation.get("previous", [])],
    }
    return result


@app.command("finalize")
def finalize_command(
    installation: Path,
    upgrade: Path,
    snapshot: Path,
    output: Path,
    schema: str = typer.Option(...),
    release_directory: str = typer.Option(...),
) -> None:
    merged = finalize(
        json.loads(installation.read_text()),
        json.loads(upgrade.read_text()),
        json.loads(snapshot.read_text()),
        schema=schema,
        release_directory=release_directory,
    )
    output.write_text(json.dumps(merged, indent=2) + "\n")
    typer.echo("PASS: upgrade receipt")
