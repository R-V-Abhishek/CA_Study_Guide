"""Build and verify offline release bundles; never deploy or modify live storage."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

import typer

from caf_cli.host_bundle import (
    FileRecord, ImageRecord, LOCKS, Manifest, PAYLOAD, check_manifest, digest, verify_archive,
)

ROOT = Path(__file__).resolve().parents[1]
app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


def run(arguments: list[str], *, cwd: Path = ROOT, **kwargs) -> str:
    return subprocess.check_output(arguments, cwd=cwd, text=True, **kwargs).strip()


def source_identity(root: Path, candidate: bool) -> tuple[str, str]:
    if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root):
        raise ValueError("Release packaging requires a clean working tree, including untracked files")
    commit = run(["git", "rev-parse", "HEAD"], cwd=root)
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = "v" + project["version"]
    if not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Application version must be stable Semantic Versioning")
    locks = tomllib.loads((root / "uv.lock").read_text())
    locked = next(package for package in locks["package"] if package["name"] == project["name"])
    if locked["version"] != project["version"]:
        raise ValueError("Project version differs from uv.lock")
    if not candidate:
        tagged = run(["git", "rev-parse", "--verify", f"refs/tags/{version}^{{commit}}"], cwd=root)
        if tagged != commit:
            raise ValueError("Release tag must point at the clean checked-out commit")
    return version, commit


@app.command()
def verify(bundle: Path, platform: str | None = None, allow_candidate: bool = False,
           load: bool = False) -> None:
    """Verify all file hashes before loading; candidate bundles require explicit opt-in."""
    manifest = verify_archive(bundle)
    if manifest.candidate and not allow_candidate:
        raise ValueError("Candidate bundles cannot be selected as production releases")
    if platform and manifest.platform != platform:
        raise ValueError("Bundle architecture does not match the selected destination")
    if load:
        with tempfile.TemporaryDirectory(prefix="caf-load-") as temporary:
            path = Path(temporary) / "images.tar"
            with tarfile.open(bundle, "r:gz") as archive, path.open("wb") as destination:
                with archive.extractfile("images.tar") as origin:
                    shutil.copyfileobj(origin, destination)
            subprocess.run(["docker", "image", "load", "-i", str(path)], check=True)
        for record in (manifest.application, manifest.postgres):
            image = json.loads(run(["docker", "image", "inspect", record.reference]))[0]
            if image["Id"] != record.image_id or f"{image['Os']}/{image['Architecture']}" != manifest.platform:
                raise ValueError("Loaded image identity or architecture differs from manifest")
        labels = json.loads(run(["docker", "image", "inspect", manifest.application.reference]))[0]["Config"]["Labels"]
        if labels["org.opencontainers.image.revision"] != manifest.commit or labels["org.opencontainers.image.version"] != manifest.version:
            raise ValueError("Loaded application version differs from manifest")
    typer.echo(f"PASS: {manifest.version} {manifest.commit} {manifest.platform}; all bundle checksums")


@app.command()
def build(
    platform: str = "linux/amd64",
    output: Path = ROOT / "release-output",
    candidate: bool = False,
    buildx: str = "docker",
) -> None:
    """Build committed source, verify the real stack, export both images and checksum."""
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise ValueError("Supported platforms are linux/amd64 and linux/arm64")
    version, commit = source_identity(ROOT, candidate)
    compatibility = tomllib.loads((ROOT / "deploy/compatibility.toml").read_text())
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    head = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    if compatibility["required_schema"] != head:
        raise ValueError("Compatibility record must name the current migration head")
    if compatibility["supported_schemas"] != [head]:
        raise ValueError("Additional schema compatibility needs a separate tested rollback drill")
    suffix = f"-candidate-{commit[:12]}" if candidate else ""
    name = f"caf-{version}{suffix}-{platform.replace('/', '-')}"
    reference = f"caf:{version}{suffix}-{platform.split('/')[1]}"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = output / f"{name}.tar.gz"
    sidecar = bundle.with_name(bundle.name + ".sha256")
    if bundle.exists() or sidecar.exists():
        raise ValueError("Refusing to overwrite an existing immutable bundle")
    created = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="caf-release-") as temporary:
        directory = Path(temporary)
        # A git archive makes the build context independent of ignored local files.
        source = directory / "source"
        source.mkdir()
        snapshot = directory / "source.tar"
        subprocess.run(["git", "archive", "--format=tar", "-o", str(snapshot), commit], cwd=ROOT, check=True)
        with tarfile.open(snapshot) as archive:
            archive.extractall(source, filter="data")
        metadata = directory / "build-metadata.json"
        prefix = ["docker", "buildx"] if buildx == "docker" else [buildx]
        environment = os.environ.copy()
        environment["BUILDX_METADATA_PROVENANCE"] = "max"
        subprocess.run([*prefix, "build", "--platform", platform, "--load", "--provenance=false",
            "--build-arg", f"SOURCE_REVISION={commit}", "--build-arg", f"APPLICATION_VERSION={version}",
            "--build-arg", f"BUILD_TIMESTAMP={created.isoformat()}", "--metadata-file", str(metadata),
            "-t", reference, str(source)], check=True, env=environment)
        image = json.loads(run(["docker", "image", "inspect", reference]))[0]
        if f"{image['Os']}/{image['Architecture']}" != platform:
            raise ValueError("Built image architecture mismatch")
        labels = image["Config"]["Labels"]
        if labels["org.opencontainers.image.revision"] != commit or labels["org.opencontainers.image.version"] != version:
            raise ValueError("Built image source identity mismatch")
        subprocess.run(["sh", str(source / "deploy/verify-image.sh"), reference], check=True)
        subprocess.run(["uv", "run", "--no-sync", str(ROOT / "scripts/verify_host_launcher.py"),
                        "--image", reference], cwd=ROOT, check=True)
        subprocess.run(["docker", "pull", "--platform", platform, "postgres:16-bookworm"], check=True)
        receipt = directory / "stack-verification.json"
        subprocess.run(["uv", "run", "--no-sync", str(ROOT / "scripts/verify_production_stack.py"),
                        "--image", reference, "--report", str(receipt)], cwd=ROOT, check=True)
        tested = json.loads(receipt.read_text())
        if not tested["passed"] or not tested["cleanup_succeeded"] or tested["image_id"] != image["Id"]:
            raise ValueError("Stack verification failed or tested a different image")
        # Capture the exact database image that the disposable stack just exercised.
        database = json.loads(run(["docker", "image", "inspect", tested["postgres_image_id"]]))[0]
        if f"{database['Os']}/{database['Architecture']}" != platform:
            raise ValueError("Database image architecture differs; run on a matching builder host")
        database_reference = "caf-postgres:" + database["Id"].split(":")[1]
        subprocess.run(["docker", "tag", database["Id"], database_reference], check=True)
        subprocess.run(["docker", "image", "save", "-o", str(directory / "images.tar"),
                        reference, database_reference], check=True)
        for original, name_in_bundle in (("compose.production.yml", "compose.production.yml"),
            ("deploy/host.env.example", "host.env.example"), ("deploy/verify-image.sh", "verify-image.sh"),
            ("CHANGELOG.md", "RELEASE_NOTES.md")):
            shutil.copyfile(source / original, directory / name_in_bundle)
        manifest = Manifest(version=version, candidate=candidate, commit=commit, platform=platform,
            created_at=created, application=ImageRecord(reference=reference, image_id=image["Id"]),
            postgres=ImageRecord(reference=database_reference, image_id=database["Id"]),
            required_schema=head, supported_schemas=compatibility["supported_schemas"],
            dependency_locks={name: digest(source / name) for name in LOCKS},
            files={name: FileRecord(sha256=digest(directory / name), size=(directory / name).stat().st_size)
                   for name in PAYLOAD})
        check_manifest(manifest)
        (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
        names = PAYLOAD | {"manifest.json"}
        (directory / "SHA256SUMS").write_text("".join(f"{digest(directory / name)}  {name}\n" for name in sorted(names)))
        # Publish only after packaging and verification succeed; partial files remain temporary.
        packed = directory / bundle.name
        with tarfile.open(packed, "w:gz", compresslevel=6) as archive:
            for name in sorted(names | {"SHA256SUMS"}):
                archive.add(directory / name, arcname=name, recursive=False)
        packed.with_name(packed.name + ".sha256").write_text(f"{digest(packed)}  {packed.name}\n")
        verify_archive(packed)
        if source_identity(ROOT, candidate) != (version, commit):
            raise ValueError("Source changed while packaging")
        # Exclusive creation also prevents overwrites by overlapping packaging invocations.
        with bundle.open("xb") as destination, packed.open("rb") as origin:
            shutil.copyfileobj(origin, destination)
        with sidecar.open("x") as destination:
            destination.write(f"{digest(bundle)}  {bundle.name}\n")
    typer.echo(f"PASS: verified {'candidate' if candidate else 'release'} bundle: {bundle}")


if __name__ == "__main__":
    app()
