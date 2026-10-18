"""Synthetic probes sent over stdin to an owned integration container."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
import typer

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
NODE = "integration.subtopic"
ACCOUNTS = (101, 102, 103)


def guard() -> None:
    if os.environ.get("CAF_INTEGRATION") != "owned-synthetic-stack":
        raise RuntimeError("This probe requires an explicitly owned synthetic stack")


def database():
    guard()
    from caf_db.engine import get_engine
    return get_engine("migration")


@app.command()
def seed() -> None:
    from sqlalchemy.orm import Session
    from caf_api.auth import hash_token
    from caf_db.models.app import AuthSession, Note, Progress, Settings, UserAccount
    from caf_db.models.ref import Attempt, Node, Paper, Scheme

    with Session(database()) as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(UserAccount)) <= 1
        session.add(Scheme(id="integration", name="Synthetic integration scheme"))
        # Identity migration 0003 already creates the May 2027 planning attempt.
        assert session.get(Attempt, "2027-05").exam_year == 2027
        session.flush()
        session.add(Paper(id="integration.P1", scheme_id="integration", code="P1",
                          name="Synthetic integration paper", group_no=1, is_current=True))
        session.flush()
        session.add(Node(id="integration.chapter", paper_id="integration.P1", level="chapter",
                         name="Synthetic integration chapter", seq=1, status="active"))
        session.flush()
        session.add(Node(id="integration.topic", paper_id="integration.P1", level="topic",
                         parent_id="integration.chapter", name="Synthetic integration topic", seq=1, status="active"))
        session.flush()
        session.add(Node(id=NODE, paper_id="integration.P1", level="subtopic", parent_id="integration.topic",
                         name="Synthetic integration topic", seq=1, status="active"))
        now = datetime.now(timezone.utc)
        tokens = json.loads(os.environ["CAF_INTEGRATION_TOKENS"])
        for account in ACCOUNTS:
            session.add(UserAccount(id=account, name=f"Synthetic student {account}",
                issuer="integration", subject=str(account), role="student", status="active"))
        session.flush()
        for account in ACCOUNTS:
            token = tokens[str(account)]
            session.add(Settings(user_id=account, target_attempt_id="2027-05",
                                 selected_paper_ids=["integration.P1"]))
            session.add(Note(user_id=account, node_id=NODE, body=f"Synthetic integration note {account}"))
            session.add(Progress(user_id=account, node_id=NODE, status="in_progress"))
            session.add(AuthSession(token_hash=hash_token(token), user_id=account,
                csrf_token=hashlib.sha256(f"csrf:{token}".encode()).hexdigest(),
                created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1)))
        session.commit()
    Path("/srv/caf/data/integration-marker").write_text("synthetic document marker")
    Path("/srv/caf/data/backups/integration-marker").write_text("synthetic local backup marker")
    print("PASS: synthetic accounts, private records, sessions and persistent file markers", flush=True)


@app.command()
def admin() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    guard()
    for name, expected in json.loads(os.environ["CAF_INTEGRATION_CONFIG_HASHES"]).items():
        assert hashlib.sha256(Path(f"config/{name}.toml").read_bytes()).hexdigest() == expected
    with database().connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM ops.alembic_version"))
        assert revision == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        roles = connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname LIKE 'caf_%'"))
        rows = list(roles)
        assert {row[0] for row in rows} == {"caf_app", "caf_identity", "caf_curator", "caf_operations", "caf_pipeline", "caf_backup"}
        assert all(not any(row[1:]) for row in rows)
    print(f"PASS: schema {revision}, six restricted roles, exact runtime config hashes", flush=True)


def request(account: int, path: str, *, body: dict | None = None) -> tuple[int, dict]:
    token = json.loads(os.environ["CAF_INTEGRATION_TOKENS"])[str(account)]
    headers = {"Cookie": f"caf_session={token}", "Origin": os.environ["AUTH_PUBLIC_BASE_URL"],
               "X-CSRF-Token": hashlib.sha256(f"csrf:{token}".encode()).hexdigest(),
               "Content-Type": "application/json"}
    req = urllib.request.Request("http://127.0.0.1:8788" + path, headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
        method="PUT" if body is not None else "GET")
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


@app.command()
def web(update: bool = False) -> None:
    guard()
    assert os.getuid() == 10001
    assert os.environ["CAF_ENV"] == "production" and os.environ["AUTH_LOCAL_DEVELOPMENT"] == "false"
    assert not os.environ["GEMINI_API_KEY"] and not os.environ["OPENROUTER_API_KEY"]
    def account_check(account: int) -> None:
        status, me = request(account, "/api/v1/me")
        assert status == 200 and me["account"]["id"] == account
        status, search = request(account, "/api/v1/search?q=integration&include_notes=true")
        assert status == 200
        assert len(search["notes"]) == 1
        assert search["notes"][0]["content"].endswith(str(account))
        assert request(account, "/api/v1/admin/accounts")[0] == 403
        if update:
            status, _ = request(account, f"/api/v1/subtopics/{NODE}/notes",
                                body={"notes": f"Updated synthetic integration note {account}"})
            assert status == 200
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(account_check, ACCOUNTS))
    for role in ("STUDENT", "IDENTITY", "CURATION", "OPERATIONS", "BACKUP"):
        assert os.environ[f"{role}_DATABASE_URL"]
    assert "MIGRATION_DATABASE_URL" not in os.environ
    assert Path("/srv/caf/data/integration-marker").read_text() == "synthetic document marker"
    assert Path("/srv/caf/data/backups/integration-marker").read_text() == "synthetic local backup marker"
    print("PASS: three concurrent authenticated accounts, private notes, mutation and admin denial", flush=True)


@app.command()
def durable() -> None:
    with database().connect() as connection:
        rows = connection.execute(sa.text("SELECT user_id,body FROM app.note WHERE user_id BETWEEN 101 AND 103 ORDER BY user_id")).all()
        assert [(row[0], row[1]) for row in rows] == [(a, f"Updated synthetic integration note {a}") for a in ACCOUNTS]
        assert connection.scalar(sa.text("SELECT count(*) FROM app.progress WHERE user_id BETWEEN 101 AND 103 AND status='in_progress'")) == 3
    print("PASS: durable ownership, notes and progress", flush=True)


@app.command()
def restricted(role: str) -> None:
    guard()
    from caf_db.engine import get_engine
    assert os.getuid() == 10001
    with get_engine(role).connect() as connection:
        assert connection.scalar(sa.text("SELECT current_user")) == f"caf_{role}"
        connection.execute(sa.text("SELECT id FROM ref.paper LIMIT 1"))
        try:
            connection.execute(sa.text("SELECT body FROM app.note LIMIT 1"))
        except DBAPIError as error:
            assert error.orig.sqlstate == "42501"
            connection.rollback()
        else:
            raise AssertionError(f"{role} can read private notes")
    print(f"PASS: {role} role reads shared references and cannot read private notes", flush=True)


@app.command()
def enqueue(expired: bool = False) -> None:
    from sqlalchemy.orm import Session
    from caf_l5.jobs import enqueue_recompute
    with Session(database()) as session:
        job = enqueue_recompute(session, "2027-05")
        if expired:
            job.status = "running"
            job.lease_token = "synthetic-interrupted-lease"
            job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            job.attempts = 1
            session.commit()
    print("PASS: enqueued expired lease" if expired else "PASS: enqueued scoring job", flush=True)


@app.command()
def completed(reclaimed: bool = False) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with database().connect() as connection:
            row = connection.execute(sa.text("SELECT status,attempts,last_error FROM intel.recompute_job ORDER BY id DESC LIMIT 1")).one()
        if row.status == "failed":
            raise RuntimeError(f"Synthetic worker job failed: {row.last_error}")
        if row.status == "ok":
            assert row.attempts >= (2 if reclaimed else 1)
            print("PASS: worker reclaimed expired lease" if reclaimed else "PASS: worker completed scoring job", flush=True)
            return
        time.sleep(0.25)
    raise RuntimeError("Worker job did not complete within 45 seconds")


if __name__ == "__main__":
    app()
