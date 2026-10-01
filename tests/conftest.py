"""Start isolation before collection; committed tests get independent database clones."""

import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
from uuid import uuid4

import pytest

_sandbox = None
_storage = None
_connect = None
_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex
_admin = None


def pytest_sessionstart(session):
    global _sandbox, _storage, _connect, _admin
    # These values are set before any application imports or test collection.
    os.environ["CAF_TEST_MODE"] = "1"
    os.environ["CAF_TEST_DATABASE_ALLOWLIST"] = "[]"
    _storage = tempfile.TemporaryDirectory(prefix="caf-pytest-")
    os.environ["CAF_TEST_STORAGE_ROOT"] = _storage.name
    os.environ["CAF_TEST_ARTIFACT_ROOT"] = str(session.config._tmp_path_factory.getbasetemp())
    os.environ["GEMINI_API_KEY"] = ""
    for role in ("APP", "CURATOR", "PIPELINE"):
        os.environ[f"PG_{role}_PASSWORD"] = secrets.token_hex(16)

    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    import sqlalchemy as sa
    from caf_common.db_safety import assert_safe_database
    from caf_common.postgres_sandbox import PostgresSandbox

    _connect = psycopg.connect

    def guarded_connect(conninfo="", **kwargs):
        params = conninfo_to_dict(conninfo)
        params.update({k: v for k, v in kwargs.items() if k in
                       {"host", "port", "dbname", "user", "password", "options", "service", "hostaddr"}})
        if any(params.get(k) for k in ("options", "service", "hostaddr")):
            raise RuntimeError("Test database connection overrides rejected")
        assert_safe_database(sa.URL.create("postgresql+psycopg", host=params.get("host"),
                                          port=int(params.get("port", 5432)),
                                          database=params.get("dbname")))
        return _connect(conninfo, **kwargs)

    psycopg.connect = guarded_connect

    def guarded_socket_connect(sock, address):
        allowed = json.loads(os.environ["CAF_TEST_DATABASE_ALLOWLIST"])
        endpoints = {(host, port) for host, port, _ in allowed}
        if sock.family in (socket.AF_INET, socket.AF_INET6) and tuple(address[:2]) not in endpoints:
            raise RuntimeError("External network/model acquisition disabled in tests")
        return _socket_connect(sock, address)

    def guarded_socket_connect_ex(sock, address):
        guarded_socket_connect(sock, address)
        return 0

    socket.socket.connect = guarded_socket_connect
    socket.socket.connect_ex = guarded_socket_connect_ex
    try:
        _sandbox = PostgresSandbox("tests").__enter__()
        _sandbox.allow("caf_template")
        _admin = sa.create_engine(_sandbox.url(), isolation_level="AUTOCOMMIT")
        with _admin.connect() as conn:
            conn.execute(sa.text("CREATE DATABASE caf_template"))
        _configure("caf_template", Path(_storage.name) / "collection")

        from alembic import command
        from alembic.config import Config
        from caf_db.engine import get_engine, reset_database
        from caf_db.grants import apply_grants
        from caf_db.models.app import UserAccount, Settings
        from caf_db.models.ops import Run
        from caf_l0.loader import TaxonomyLoader
        from sqlalchemy.orm import Session

        command.upgrade(Config("alembic.ini"), "head")
        apply_grants()
        engine = get_engine()
        with Session(engine) as db:
            loader = TaxonomyLoader()
            loader.apply(db, loader.plan())
            db.add(UserAccount(id=1, name="Isolated fixture student"))
            db.flush()
            db.add(Settings(user_id=1, target_attempt_id="2026-05"))
            db.add(Run(id=1, stage="test-fixture", status="ok", stats={}))
            db.commit()
            db.execute(sa.text("SELECT setval('ops.run_id_seq', 1)"))
            db.commit()
        reset_database()
        with _admin.connect() as conn:
            conn.execute(sa.text("ALTER DATABASE caf_template WITH ALLOW_CONNECTIONS false"))
    except BaseException:
        _cleanup()
        raise


def _configure(database, storage):
    from caf_common.settings import reset_settings
    from caf_db.engine import reset_database
    reset_database()
    os.environ["DATABASE_URL"] = _sandbox.url(database).render_as_string(hide_password=False)
    os.environ["PG_HOST"] = "127.0.0.1"
    os.environ["PG_PORT"] = str(_sandbox.port)
    os.environ["PG_DATABASE"] = database
    os.environ["PG_SUPERUSER"] = "postgres"
    os.environ["PG_SUPERUSER_PASSWORD"] = _sandbox.password
    os.environ["CAF_TEST_STORAGE_ROOT"] = str(storage)
    reset_settings()


@pytest.fixture(autouse=True)
def isolated_database():
    import sqlalchemy as sa
    from caf_db.engine import reset_database
    from caf_common.db_safety import disallow_test_database
    database = f"caf_test_{uuid4().hex}"
    _sandbox.allow(database)
    with _admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{database}" TEMPLATE caf_template'))
    _configure(database, Path(_storage.name) / database)
    try:
        yield _sandbox
    finally:
        reset_database()
        with _admin.connect() as conn:
            # Only the just-created, uniquely named test database is removed.
            conn.execute(sa.text(f'DROP DATABASE "{database}"'))
        disallow_test_database("127.0.0.1", _sandbox.port, database)


@pytest.fixture
def session():
    from caf_db.engine import get_session_factory
    with get_session_factory()() as db:
        yield db


def _cleanup():
    global _sandbox
    if _admin is not None:
        _admin.dispose()
    if _sandbox is not None:
        _sandbox.close()
        _sandbox = None
    if _connect is not None:
        import psycopg
        psycopg.connect = _connect
    socket.socket.connect = _socket_connect
    socket.socket.connect_ex = _socket_connect_ex
    if _storage is not None:
        _storage.cleanup()


def pytest_sessionfinish(session, exitstatus):
    from caf_db.engine import reset_database
    reset_database()
    _cleanup()
