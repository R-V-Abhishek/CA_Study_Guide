"""Packaged install planning and restore validation; Docker stays on the host."""

import json
from pathlib import Path
import re
import tarfile
from urllib.parse import urlsplit

import typer

from caf_cli.host_bundle import digest, saved_image_ids, verify_archive
from caf_common.recovery_manifest import checksum, inspect_recovery_files

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def prepare(bundle: Path, snapshot: Path, rendered: Path, output: Path,
            destination: str = typer.Option(...), project: str = typer.Option(...),
            port: int = 8788, allow_candidate: bool = False) -> None:
    """Validate inputs and write the private effective Compose file plus a receipt."""
    manifest = verify_archive(bundle)
    backup = inspect_recovery_files(snapshot)
    from caf_common.backup import critical_tables
    if critical_tables(backup.database_revision) - backup.tables.keys():
        raise ValueError("Protected tables missing from backup")
    if manifest.candidate and not allow_candidate:
        raise ValueError("Candidate installation requires explicit --allow-candidate")
    if backup.database_revision not in manifest.supported_schemas:
        raise ValueError("Release does not support the backup schema")
    if not re.fullmatch(r"caf(?:-install-[a-z0-9]+)?", project):
        raise ValueError("Use project caf or caf-install-<unique-id>")
    root = Path(destination)
    if not root.is_absolute() or root == Path("/") or not 0 <= port <= 65535:
        raise ValueError("Invalid destination or loopback port")
    configuration = json.loads(rendered.read_text())
    services = configuration["services"]
    if set(services) != {"db", "web", "worker", "admin", "pipeline"}:
        raise ValueError("Expected the production services and manual tools")
    admin = services["admin"]["environment"]
    passwords = [services["db"]["environment"]["POSTGRES_PASSWORD"],
                 *[admin[f"PG_{role}_PASSWORD"] for role in
                   ("APP", "IDENTITY", "CURATOR", "OPERATIONS", "PIPELINE", "BACKUP")]]
    if len(set(passwords)) != 7 or any(not re.fullmatch(r"[0-9a-f]{64,}", value) for value in passwords):
        raise ValueError("Seven distinct hexadecimal production database passwords required")
    web = services["web"]["environment"]
    public = urlsplit(web["AUTH_PUBLIC_BASE_URL"])
    issuer = urlsplit(web["OIDC_ISSUER"])
    if (public.scheme != "https" or issuer.scheme != "https" or not public.hostname or not issuer.hostname
            or not web["OIDC_CLIENT_ID"] or not web["OIDC_CLIENT_SECRET"]):
        raise ValueError("HTTPS application URL and Auth0 configuration required")
    if not manifest.candidate and not public.hostname.endswith(".ts.net"):
        raise ValueError("Production application URL must use the assigned private ts.net hostname")
    paths = {"/srv/caf/data": "data", "/srv/caf/backups": "backups", "/srv/caf/postgres": "postgres"}
    for name, service in services.items():
        expected = manifest.postgres.reference if name == "db" else manifest.application.reference
        if service["image"] != expected or service["platform"] != manifest.platform:
            raise ValueError("Compose images or architecture differ from verified release")
        service["pull_policy"] = "never"
        service["labels"] = {"caf.managed": "host-installer", "caf.installation": project}
        for mount in service["volumes"]:
            if mount["type"] != "bind" or mount["source"] not in paths:
                raise ValueError("Unexpected production storage mount")
            mount["source"] = str(root / paths[mount["source"]])
            mount.setdefault("bind", {})["create_host_path"] = False
        # Keep Compose's canonical dollar escaping intact when this JSON is
        # parsed again; escaping it a second time would change credentials.
    services["web"]["ports"][0]["published"] = str(port)
    configuration["name"] = project
    for name, network in configuration["networks"].items():
        network["name"] = f"{project}_{name}"
    (output / "compose.json").write_text(json.dumps(configuration, indent=2) + "\n")
    receipt = {"format_version": 1, "phase": "prepared", "project": project,
               "destination": destination, "application": manifest.model_dump(mode="json"),
               "backup_manifest_sha256": checksum(snapshot / "manifest.json"),
               "bundle_sha256": digest(bundle), "dump_file": backup.dump_file,
               "database_revision": backup.database_revision}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


@app.command()
def loaded(bundle: Path, metadata: Path) -> None:
    """Verify loaded Docker identities before any application storage changes."""
    manifest = verify_archive(bundle)
    receipt_path = metadata.parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if digest(bundle) != receipt["bundle_sha256"]:
        raise ValueError("Bundle changed after install planning")
    actual = {tag: item for item in json.loads(metadata.read_text()) for tag in item["RepoTags"]}
    with tarfile.open(bundle) as outer, outer.extractfile("images.tar") as stream:
        with tarfile.open(fileobj=stream, mode="r:") as images:
            for record in (manifest.application, manifest.postgres):
                image = actual[record.reference]
                if (image["Id"] not in saved_image_ids(images, record)
                        or f"{image['Os']}/{image['Architecture']}" != manifest.platform):
                    raise ValueError("Loaded image differs from the verified archive")
    labels = actual[manifest.application.reference]["Config"]["Labels"]
    if labels["org.opencontainers.image.revision"] != manifest.commit or labels["org.opencontainers.image.version"] != manifest.version:
        raise ValueError("Loaded application labels differ from the release")
    configuration_path = metadata.parent / "compose.json"
    configuration = json.loads(configuration_path.read_text())
    for name, service in configuration["services"].items():
        reference = manifest.postgres.reference if name == "db" else manifest.application.reference
        service["image"] = actual[reference]["Id"]
    configuration_path.write_text(json.dumps(configuration, indent=2) + "\n")
    receipt["loaded_images"] = {reference: image["Id"] for reference, image in actual.items()}
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    typer.echo("PASS: loaded release identities")


@app.command()
def restored(snapshot: Path, expected_manifest_hash: str = typer.Option(...)) -> None:
    """Check restored bytes and database rows before migrations and session revocation."""
    from caf_common.backup import compare_restored_database, critical_tables
    from caf_db.engine import database_url

    if checksum(snapshot / "manifest.json") != expected_manifest_hash:
        raise ValueError("Backup manifest changed after install planning")
    manifest = inspect_recovery_files(snapshot)
    if critical_tables(manifest.database_revision) - manifest.tables.keys():
        raise ValueError("Protected tables missing from backup")
    url = database_url("migration")
    if (url.host, url.port, url.database, url.username) != ("db", 5432, "caf", "postgres") or url.query:
        raise ValueError("Restore comparison must use the install project's internal database")
    counts, _ = compare_restored_database(url, manifest.model_dump(by_alias=True))
    data = Path("/srv/caf/data")
    for relative, expected in manifest.files.items():
        source = Path(relative)
        target = data / (source if source.parts[0] == "blobs" else Path("recovery-configs") / source.relative_to("configs"))
        if checksum(target) != expected:
            raise ValueError("Restored file checksum mismatch")
    typer.echo(json.dumps({"restored_tables": len(counts), "restored_files": len(manifest.files), "verified": True}))
