"""Connection boundary used by the disposable test harness, including subprocesses."""

import json
import os
from pathlib import Path
from sqlalchemy.engine import URL, make_url


def assert_safe_database(url: str | URL) -> None:
    """In tests, accept only explicit harness-owned endpoint/database pairs."""
    if os.environ.get("CAF_TEST_MODE") != "1":
        return
    target = make_url(url)
    allowed = json.loads(os.environ.get("CAF_TEST_DATABASE_ALLOWLIST", "[]"))
    key = [target.host, target.port, target.database]
    if target.get_backend_name() != "postgresql" or key not in allowed or target.query:
        raise RuntimeError("Test database target rejected: outside harness allowlist")


def allow_test_database(host: str, port: int, database: str) -> None:
    if os.environ.get("CAF_TEST_MODE") == "1":
        allowed = json.loads(os.environ.get("CAF_TEST_DATABASE_ALLOWLIST", "[]"))
        key = [host, port, database]
        if key not in allowed:
            allowed.append(key)
            os.environ["CAF_TEST_DATABASE_ALLOWLIST"] = json.dumps(allowed)


def disallow_test_database(host: str, port: int, database: str) -> None:
    if os.environ.get("CAF_TEST_MODE") == "1":
        allowed = json.loads(os.environ.get("CAF_TEST_DATABASE_ALLOWLIST", "[]"))
        key = [host, port, database]
        os.environ["CAF_TEST_DATABASE_ALLOWLIST"] = json.dumps([x for x in allowed if x != key])


def assert_safe_storage(path: Path) -> None:
    if os.environ.get("CAF_TEST_MODE") == "1":
        roots = [Path(os.environ[key]).resolve() for key in
                 ("CAF_TEST_STORAGE_ROOT", "CAF_TEST_ARTIFACT_ROOT") if os.environ.get(key)]
        if not any(path.resolve().is_relative_to(root) for root in roots):
            raise RuntimeError("Test storage target rejected: outside harness temporary directories")


def assert_acquisition_allowed() -> None:
    """Also protect CLI subprocesses, which do not inherit pytest's socket patch."""
    if os.environ.get("CAF_TEST_MODE") == "1":
        raise RuntimeError("External network acquisition disabled in tests")
