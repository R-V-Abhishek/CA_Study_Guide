"""Owned, temporary PostgreSQL 16 containers for tests and recovery drills.

Uses the active Docker context (including Colima); never touches Compose volumes.
"""

from dataclasses import dataclass, field
import secrets
import subprocess
import time
from uuid import uuid4

from sqlalchemy.engine import URL
from caf_common.db_safety import allow_test_database, disallow_test_database


@dataclass
class PostgresSandbox:
    purpose: str
    use_tmpfs: bool = True
    name: str = field(init=False)
    password: str = field(default_factory=lambda: secrets.token_hex(24))
    port: int = field(init=False, default=0)
    databases: set[str] = field(default_factory=set)
    started: bool = False

    def __post_init__(self) -> None:
        self.name = f"caf-{self.purpose}-{uuid4().hex[:12]}"

    def url(self, database: str = "postgres") -> URL:
        return URL.create("postgresql+psycopg", username="postgres", password=self.password,
                          host="127.0.0.1", port=self.port, database=database)

    def allow(self, database: str) -> None:
        self.databases.add(database)
        allow_test_database("127.0.0.1", self.port, database)

    def __enter__(self) -> "PostgresSandbox":
        try:
            # Large restores must not be limited by tmpfs's fraction of VM RAM.
            # --rm removes this container's own anonymous volume when it exits.
            storage = (["--tmpfs", "/var/lib/postgresql/data:rw"] if self.use_tmpfs
                       else ["--volume", "/var/lib/postgresql/data"])
            subprocess.run([
                "docker", "run", "--detach", "--rm", "--name", self.name,
                "--label", "caf.disposable=true", *storage,
                "--publish", "127.0.0.1::5432", "--env", f"POSTGRES_PASSWORD={self.password}",
                "postgres:16",
            ], check=True, capture_output=True, text=True)
            self.started = True
            mapping = subprocess.run(["docker", "port", self.name, "5432/tcp"],
                                     check=True, capture_output=True, text=True).stdout.strip()
            self.port = int(mapping.rsplit(":", 1)[1])
            self.allow("postgres")
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                # The image's init server accepts Unix sockets before its final
                # TCP server starts. Wait for the same TCP endpoint clients use.
                result = subprocess.run(["docker", "exec", self.name, "pg_isready", "-h", "127.0.0.1",
                                         "-p", "5432", "-U", "postgres"],
                                        capture_output=True)
                if result.returncode == 0:
                    return self
                time.sleep(0.25)
            raise RuntimeError("Disposable PostgreSQL did not become ready in 60 seconds")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.started:
            subprocess.run(["docker", "stop", "--time", "1", self.name],
                           check=True, capture_output=True)
            self.started = False
        for database in self.databases:
            disallow_test_database("127.0.0.1", self.port, database)

    def __exit__(self, *exc) -> None:
        self.close()
