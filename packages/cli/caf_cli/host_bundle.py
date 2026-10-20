"""Versioned offline application-bundle contract shared by builder and host tooling."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import tarfile

from pydantic import BaseModel, ConfigDict, Field

PAYLOAD = {"images.tar", "compose.production.yml", "host.env.example", "RELEASE_NOTES.md",
           "verify-image.sh", "build-metadata.json", "stack-verification.json"}
LOCKS = ("uv.lock", "web/pnpm-lock.yaml")


class FileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)


class ImageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(pattern=r"^caf(?:-postgres)?:[a-zA-Z0-9_.-]+$")
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: int = Field(default=1, ge=1, le=1)
    version: str = Field(pattern=r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    candidate: bool
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    platform: str = Field(pattern=r"^linux/(amd64|arm64)$")
    created_at: datetime
    application: ImageRecord
    postgres: ImageRecord
    required_schema: str
    supported_schemas: list[str]
    dependency_locks: dict[str, str]
    files: dict[str, FileRecord]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_manifest(manifest: Manifest) -> None:
    if set(manifest.files) != PAYLOAD:
        raise ValueError("Unexpected or missing release payload files")
    if set(manifest.dependency_locks) != set(LOCKS):
        raise ValueError("Both dependency lock hashes are required")
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in manifest.dependency_locks.values()):
        raise ValueError("Invalid dependency lock hash")
    if not manifest.required_schema or manifest.required_schema not in manifest.supported_schemas:
        raise ValueError("Required schema must be explicitly supported")
    if len(manifest.supported_schemas) != len(set(manifest.supported_schemas)):
        raise ValueError("Duplicate supported schemas")
    suffix = f"-candidate-{manifest.commit[:12]}" if manifest.candidate else ""
    if manifest.application.reference != f"caf:{manifest.version}{suffix}-{manifest.platform.split('/')[1]}":
        raise ValueError("Application image reference differs from release identity")
    if manifest.postgres.reference != "caf-postgres:" + manifest.postgres.image_id.split(":")[1]:
        raise ValueError("Database image reference differs from immutable identity")


def verify_archive(bundle: Path) -> Manifest:
    """Stream members without extraction; reject links, duplicates, paths and corruption."""
    expected = bundle.with_name(bundle.name + ".sha256").read_text()
    if expected != f"{digest(bundle)}  {bundle.name}\n":
        raise ValueError("Outer bundle SHA-256 mismatch")
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or set(names) != PAYLOAD | {"manifest.json", "SHA256SUMS"}:
            raise ValueError("Unexpected, duplicate or missing bundle members")
        if any(not member.isfile() or member.size > 20 * 1024**3 for member in members):
            raise ValueError("Bundle must contain bounded regular files only")
        member = archive.getmember("manifest.json")
        if member.size > 128 * 1024:
            raise ValueError("Manifest exceeds size limit")
        manifest_bytes = archive.extractfile(member).read()
        manifest = Manifest.model_validate_json(manifest_bytes)
        check_manifest(manifest)
        hashes = {"manifest.json": hashlib.sha256(manifest_bytes).hexdigest()}
        for name, record in manifest.files.items():
            member = archive.getmember(name)
            if member.size != record.size:
                raise ValueError(f"Payload size mismatch: {name}")
            with archive.extractfile(member) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != record.sha256:
                raise ValueError(f"Payload SHA-256 mismatch: {name}")
            hashes[name] = actual
        sums = "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes))
        if archive.getmember("SHA256SUMS").size != len(sums):
            raise ValueError("Invalid SHA256SUMS size")
        if archive.extractfile("SHA256SUMS").read().decode() != sums:
            raise ValueError("Invalid SHA256SUMS")
    return manifest


def archived_image_ids(path: Path, record: ImageRecord) -> set[str]:
    """Bind classic config IDs and containerd manifest IDs to the saved image."""
    with tarfile.open(path) as archive:
        return saved_image_ids(archive, record)


def saved_image_ids(archive: tarfile.TarFile, record: ImageRecord) -> set[str]:
    def read(name: str) -> bytes:
        member = archive.getmember(name)
        if not member.isfile() or member.size > 2 * 1024**2:
            raise ValueError(f"Invalid saved image metadata: {name}")
        return archive.extractfile(member).read()

    entries = json.loads(read("manifest.json"))
    matching = [entry for entry in entries if record.reference in entry["RepoTags"]]
    if len(matching) != 1:
        raise ValueError("Saved image reference must identify exactly one image")
    config_id = "sha256:" + hashlib.sha256(read(matching[0]["Config"])).hexdigest()
    identities = {config_id}
    if "index.json" in archive.getnames():
        for descriptor in json.loads(read("index.json"))["manifests"]:
            if descriptor["mediaType"] != "application/vnd.oci.image.manifest.v1+json":
                continue
            manifest_id = descriptor["digest"]
            algorithm, value = manifest_id.split(":", 1)
            if algorithm != "sha256" or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("Invalid saved image manifest digest")
            payload = read(f"blobs/sha256/{value}")
            if hashlib.sha256(payload).hexdigest() != value:
                raise ValueError("Saved image manifest digest mismatch")
            if json.loads(payload)["config"]["digest"] == config_id:
                identities.add(manifest_id)
    if record.image_id not in identities:
        raise ValueError("Recorded image identity differs from saved image metadata")
    return identities

