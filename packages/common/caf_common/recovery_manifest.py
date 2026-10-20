"""Read-only validation of the existing format-1 recovery artifact."""

from datetime import datetime
import hashlib
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Checksum = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class TableDigest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int = Field(ge=0)
    sha256: Checksum


class RecoveryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[1]
    created_at: datetime
    database_revision: str = Field(min_length=1)
    dump_file: str
    dump_sha256: Checksum
    tables: dict[str, TableDigest]
    schema_snapshot: dict = Field(alias="schema")
    files: dict[str, Checksum]
    digest_format: str
    secrets: str


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_recovery_files(root: Path) -> RecoveryManifest:
    """Check recorded bytes only; a restore drill is a separate operation."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Backup must be a regular snapshot directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Legacy or incomplete backup: regular manifest.json required")
    if manifest_path.stat().st_size > 16 * 1024**2:
        raise ValueError("Backup manifest exceeds size limit")
    try:
        manifest = RecoveryManifest.model_validate_json(manifest_path.read_bytes())
    except ValidationError as error:
        raise ValueError("Invalid backup manifest structure") from error
    dump_name = PurePosixPath(manifest.dump_file)
    if dump_name.name != manifest.dump_file or "\\" in manifest.dump_file or dump_name.suffix != ".dump":
        raise ValueError("Unsafe backup dump filename")
    dump = root / manifest.dump_file
    if dump.is_symlink() or not dump.is_file():
        raise ValueError("Regular backup dump required")
    if checksum(dump) != manifest.dump_sha256:
        raise ValueError("Dump checksum mismatch")
    for relative in manifest.files:
        path = PurePosixPath(relative)
        if (path.is_absolute() or ".." in path.parts or "\\" in relative
                or path.as_posix() != relative or len(path.parts) < 2
                or path.parts[0] not in {"blobs", "configs"}):
            raise ValueError("Unsafe archived file path")
    actual = set()
    for directory in (root / "blobs", root / "configs"):
        if directory.is_symlink():
            raise ValueError("Archived directories must not be symlinks")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("Archived files and directories must not be symlinks")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError("Archived entries must be regular files")
            actual.add(path.relative_to(root).as_posix())
    if actual != manifest.files.keys():
        raise ValueError("Archived file inventory mismatch (missing or unexpected files)")
    for relative, expected in manifest.files.items():
        if checksum(root / relative) != expected:
            raise ValueError("Archived file checksum mismatch")
    return manifest
