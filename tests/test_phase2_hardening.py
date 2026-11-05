"""Phase 2 hardening: bounds, headers, administrator lockout, throttled sessions, pruning, rate limits."""

from datetime import timedelta

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from caf_api import auth
from caf_api.main import app
from caf_api.ratelimit import RULES, RateLimiter
from caf_common.settings import get_settings
from caf_db.models.app import AuthSession, LoginTransaction, Note, ProgressEvent, UserAccount


def first_subtopic(client):
    tree = client.get("/api/v1/papers/s2023.P1/tree").json()
    return tree["chapters"][0]["topics"][0]["subtopics"][0]["id"]


def test_health_reveals_nothing_beyond_status():
    assert TestClient(app).get("/api/v1/health").json() == {"status": "ok"}


def test_security_headers_and_hash_bound_inline_script(authenticated_client):
    client = authenticated_client()
    api = client.get("/api/v1/health")
    assert (
        api.headers["x-content-type-options"] == "nosniff"
        and api.headers["x-frame-options"] == "DENY"
    )
    page = client.get("/curator/queue")
    policy = page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert (
        "script-src 'self' 'sha256-" in policy
        and "'unsafe-inline'" not in policy.split("style-src")[0]
    )


def test_user_text_is_bounded(authenticated_client, session):
    client = authenticated_client()
    node = first_subtopic(client)
    assert (
        client.put(f"/api/v1/subtopics/{node}/notes", json={"notes": "x" * 100_000}).status_code
        == 200
    )
    assert (
        client.put(f"/api/v1/subtopics/{node}/notes", json={"notes": "x" * 100_001}).status_code
        == 422
    )
    mock = {"paper_id": "s2023.P1", "score": 50, "max_score": 100, "taken_on": "2026-10-01"}
    assert client.post("/api/v1/mock-tests", json={**mock, "label": "l" * 201}).status_code == 422
    assert (
        client.post("/api/v1/mock-tests", json={**mock, "notes": "n" * 10_001}).status_code == 422
    )


def test_database_rejects_oversized_text_and_has_student_indexes(session):
    session.add(
        Note(
            user_id=1,
            node_id=session.scalar(
                sa.text("SELECT id FROM ref.node WHERE level='subtopic' LIMIT 1")
            ),
            body="x" * 100_001,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    names = set(session.scalars(sa.text("SELECT indexname FROM pg_indexes WHERE schemaname='app'")))
    assert {
        "ix_revision_event_user_node_at",
        "ix_mock_test_user_taken_on",
        "ix_study_session_user_id",
    } <= names
    unvalidated = session.scalars(
        sa.text(
            "SELECT conname FROM pg_constraint WHERE NOT convalidated AND conname LIKE 'check_%_length'"
        )
    ).all()
    assert unvalidated == []


def test_repeating_a_status_writes_no_event(authenticated_client, session):
    client = authenticated_client()
    node = first_subtopic(client)
    for status in ("in_progress", "in_progress", "done", "done"):
        assert (
            client.put(f"/api/v1/subtopics/{node}/progress", json={"status": status}).status_code
            == 200
        )
    transitions = session.execute(
        sa.select(ProgressEvent.from_status, ProgressEvent.to_status).order_by(ProgressEvent.id)
    ).all()
    assert transitions == [("not_started", "in_progress"), ("in_progress", "done")]


def test_last_administrator_cannot_be_removed(authenticated_client, session):
    admin = authenticated_client(user_id=1, role="administrator")
    assert admin.patch("/api/v1/admin/accounts/1", json={"role": "student"}).json() == {
        "detail": "last_administrator"
    }
    assert admin.patch("/api/v1/admin/accounts/1", json={"status": "disabled"}).status_code == 409
    authenticated_client(user_id=2, role="administrator")
    assert admin.patch("/api/v1/admin/accounts/2", json={"role": "student"}).status_code == 200
    assert admin.patch("/api/v1/admin/accounts/1", json={"role": "student"}).status_code == 409


def test_production_requires_an_explicit_migration_url(monkeypatch):
    from caf_db.engine import database_url

    settings = get_settings()
    monkeypatch.setattr(settings.app, "env", "production")
    monkeypatch.setattr(settings, "MIGRATION_DATABASE_URL", None)
    with pytest.raises(RuntimeError, match="MIGRATION_DATABASE_URL is required"):
        database_url("migration")


def test_last_seen_is_written_at_most_every_five_minutes(authenticated_client, session):
    client = authenticated_client()
    row = session.scalar(sa.select(AuthSession))
    assert client.get("/api/v1/health").status_code == 200
    client.get("/api/v1/dashboard")
    session.refresh(row)
    recent = row.last_seen_at
    client.get("/api/v1/dashboard")
    session.refresh(row)
    assert row.last_seen_at == recent
    row.last_seen_at = auth.utcnow() - timedelta(minutes=6)
    session.commit()
    client.get("/api/v1/dashboard")
    session.refresh(row)
    assert row.last_seen_at > auth.utcnow() - timedelta(minutes=1)
    # Idle expiry still reads the stored value.
    row.last_seen_at = auth.utcnow() - timedelta(hours=25)
    session.commit()
    assert client.get("/api/v1/dashboard").status_code == 401


def test_prune_removes_only_long_dead_authentication_rows(authenticated_client, session):
    authenticated_client()
    now = auth.utcnow()
    live = session.scalar(sa.select(AuthSession))
    old = [
        AuthSession(
            token_hash=f"{i}" * 64,
            user_id=1,
            csrf_token="c",
            created_at=now,
            last_seen_at=now,
            expires_at=expires,
            revoked_at=revoked,
        )
        for i, (expires, revoked) in enumerate(
            [
                (now - timedelta(days=31), None),
                (now + timedelta(days=1), now - timedelta(days=31)),
                (now - timedelta(days=2), None),
                (now + timedelta(days=1), now - timedelta(days=2)),
            ],
            start=1,
        )
    ]
    stale = LoginTransaction(
        state_hash="a" * 64,
        browser_hash="b" * 64,
        nonce="n",
        code_verifier="v",
        return_to="/",
        expires_at=now - timedelta(days=2),
    )
    fresh = LoginTransaction(
        state_hash="c" * 64,
        browser_hash="d" * 64,
        nonce="n",
        code_verifier="v",
        return_to="/",
        expires_at=now - timedelta(hours=2),
    )
    session.add_all([*old, stale, fresh])
    session.commit()
    assert auth.prune_auth_tables(session, now) == {"login_transactions": 1, "auth_sessions": 2}
    remaining = set(session.scalars(sa.select(AuthSession.token_hash)))
    assert (
        live.token_hash in remaining
        and {"3" * 64, "4" * 64} <= remaining
        and not {"1" * 64, "2" * 64} & remaining
    )
    assert session.scalars(sa.select(LoginTransaction.state_hash)).all() == ["c" * 64]


def test_token_bucket_refills_with_time():
    clock = [0.0]
    limiter = RateLimiter(clock=lambda: clock[0])
    rule = next(item for item in RULES if item.name == "search")
    assert all(limiter.check(rule, "a") is None for _ in range(rule.per_minute))
    wait = limiter.check(rule, "a")
    assert wait is not None and 0 < wait <= 1
    assert limiter.check(rule, "b") is None
    clock[0] += 1
    assert limiter.check(rule, "a") is None


def test_search_is_rate_limited_per_session(authenticated_client, monkeypatch):
    monkeypatch.setattr(app.state, "rate_limit_enabled", True)
    monkeypatch.setattr(
        app.state, "rate_limiter", RateLimiter(clock=lambda: 0.0)
    )  # no refill during the burst
    first, second = authenticated_client(user_id=1), authenticated_client(user_id=2)
    statuses = [first.get("/api/v1/search", params={"q": "lease"}).status_code for _ in range(61)]
    assert statuses[:60] == [200] * 60 and statuses[60] == 429
    blocked = first.get("/api/v1/search", params={"q": "lease"})
    assert blocked.headers["retry-after"].isdigit() and blocked.json() == {"detail": "rate_limited"}
    assert second.get("/api/v1/search", params={"q": "lease"}).status_code == 200


def test_migration_keeps_existing_oversized_text_and_leaves_its_constraint_unvalidated(session):
    """A restored snapshot may hold text beyond the new limits: it is never truncated or rejected."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).parents[1] / "packages/db/caf_db/alembic/versions/0010_bounds_and_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("bounds_and_indexes", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    node = session.scalar(sa.text("SELECT id FROM ref.node WHERE level='subtopic' LIMIT 1"))
    for _, table, _, _, name in migration.BOUNDS:
        session.execute(sa.text(f"ALTER TABLE app.{table} DROP CONSTRAINT {name}"))
    for name, _, _ in migration.INDEXES:
        session.execute(sa.text(f"DROP INDEX app.{name}"))
    session.execute(
        sa.text("INSERT INTO app.note (user_id, node_id, body) VALUES (1, :node, :body)"),
        {"node": node, "body": "x" * 100_050},
    )
    migration.op = Operations(MigrationContext.configure(session.connection()))
    migration.upgrade()

    assert (
        session.scalar(sa.text("SELECT char_length(body) FROM app.note WHERE user_id=1")) == 100_050
    )
    validated = dict(
        session.execute(
            sa.text(
                "SELECT conname, convalidated FROM pg_constraint WHERE conname IN "
                "('check_note_body_length','check_mock_test_label_length','check_mock_test_notes_length')"
            )
        ).all()
    )
    assert validated == {
        "check_note_body_length": False,
        "check_mock_test_label_length": True,
        "check_mock_test_notes_length": True,
    }
    assert {
        "ix_revision_event_user_node_at",
        "ix_mock_test_user_taken_on",
        "ix_study_session_user_id",
    } <= set(session.scalars(sa.text("SELECT indexname FROM pg_indexes WHERE schemaname='app'")))
    with pytest.raises(IntegrityError):
        session.execute(
            sa.text("INSERT INTO app.note (user_id, node_id, body) VALUES (2, :node, :body)"),
            {"node": node, "body": "y" * 100_001},
        )
    session.rollback()
