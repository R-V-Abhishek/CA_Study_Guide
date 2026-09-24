"""Content-addressed local blob store."""

import hashlib
from pathlib import Path
from typing import BinaryIO


class BlobStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, sha256_hash: str) -> Path:
        prefix1 = sha256_hash[:2]
        prefix2 = sha256_hash[2:4]
        return self.base_dir / prefix1 / prefix2 / f"{sha256_hash}.pdf"

    def put(self, data: bytes) -> tuple[str, Path]:
        """Store bytes, returning (sha256, path)."""
        sha = hashlib.sha256(data).hexdigest()
        dest = self._get_path(sha)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_path = dest.with_suffix(".tmp")
            temp_path.write_bytes(data)
            temp_path.replace(dest)
        return sha, dest

    def put_stream(self, stream: BinaryIO) -> tuple[str, Path, int]:
        """Stream data to a temporary file while hashing, then atomically place it."""
        hasher = hashlib.sha256()
        temp_dir = self.base_dir / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"stream_{Path.cwd().name}_{id(stream)}.tmp"

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

    def exists(self, sha256_hash: str) -> bool:
        return self._get_path(sha256_hash).exists()
