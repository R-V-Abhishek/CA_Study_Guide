"""Content-addressed local blob store."""

import hashlib
import re
from pathlib import Path
from typing import BinaryIO
from caf_common.db_safety import assert_safe_storage


class BlobStore:
    def __init__(self, base_dir: Path) -> None:
        assert_safe_storage(base_dir)
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, sha256_hash: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256_hash):
            raise ValueError("Blob identifier must be a lowercase SHA-256 hex digest")
        prefix1 = sha256_hash[:2]
        prefix2 = sha256_hash[2:4]
        return self._checked_path(self.base_dir / prefix1 / prefix2 / f"{sha256_hash}.pdf")

    def _checked_path(self, path: Path) -> Path:
        if not path.resolve().is_relative_to(self.base_dir.resolve()):
            raise ValueError("Blob path resolves outside the storage directory")
        return path

    def put(self, data: bytes) -> tuple[str, Path]:
        """Store bytes, returning (sha256, path)."""
        sha = hashlib.sha256(data).hexdigest()
        dest = self._get_path(sha)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._checked_path(dest.with_suffix(".tmp"))
            temp_path.write_bytes(data)
            temp_path.replace(dest)
        return sha, dest

    def put_stream(self, stream: BinaryIO) -> tuple[str, Path, int]:
        """Stream data to a temporary file while hashing, then atomically place it."""
        hasher = hashlib.sha256()
        temp_dir = self._checked_path(self.base_dir / "tmp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = self._checked_path(temp_dir / f"stream_{Path.cwd().name}_{id(stream)}.tmp")

        total_bytes = 0
        with open(temp_file, "wb") as f_out:
            while chunk := stream.read(65536):
                hasher.update(chunk)
                f_out.write(chunk)
                total_bytes += len(chunk)

        sha = hasher.hexdigest()
        dest = self._get_path(sha)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_file.replace(dest)
        else:
            temp_file.unlink(missing_ok=True)

        return sha, dest, total_bytes

    def get_path(self, sha256_hash: str) -> Path | None:
        path = self._get_path(sha256_hash)
        return path if path.exists() else None

    def read(self, sha256_hash: str) -> bytes:
        """Read and return blob bytes."""
        path = self._get_path(sha256_hash)
        if not path.exists():
            raise FileNotFoundError(f"Blob {sha256_hash} not found in store")
        return path.read_bytes()

    def exists(self, sha256_hash: str) -> bool:
        return self._get_path(sha256_hash).exists()
