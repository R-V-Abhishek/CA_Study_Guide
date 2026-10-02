"""Verify actual restricted connections, not permission checks on admin sessions."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

from caf_db.engine import get_engine


@pytest.mark.parametrize("operation", ["student", "identity", "curation", "operations", "pipeline", "backup"])
def test_serving_roles_are_not_database_administrators(operation):
    with get_engine(operation).connect() as conn:
        row = conn.execute(sa.text("SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert not any(row)


@pytest.mark.parametrize("operation,sql", [
    ("student", "SELECT * FROM app.auth_session"),
    ("student", "SELECT * FROM app.invitation"),
    ("student", "UPDATE app.user_account SET role='administrator' WHERE id=1"),
    ("student", "DELETE FROM core.decision"),
    ("student", "UPDATE ingest.document SET title='forged'"),
    ("student", "DELETE FROM intel.score_run"),
    ("curation", "SELECT * FROM app.note"),
    ("curation", "SELECT * FROM app.settings"),
    ("curation", "SELECT * FROM app.auth_session"),
    ("curation", "UPDATE ingest.document SET title='forged'"),
    ("identity", "SELECT * FROM app.note"),
    ("identity", "DELETE FROM core.decision"),
    ("operations", "SELECT * FROM app.note"),
    ("operations", "SELECT * FROM app.auth_session"),
    ("pipeline", "SELECT * FROM app.mock_test"),
    ("backup", "DELETE FROM app.auth_session"),
])
def test_database_denies_operations_outside_capability(operation, sql):
    with get_engine(operation).connect() as conn:
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(sa.text(sql))
        conn.rollback()


def test_student_can_use_personal_tables_but_not_new_identity_defaults(session):
    from caf_db.grants import apply_grants
    from caf_db.models.app import UserAccount
    session.add(UserAccount(id=2, name="Second fixture"))
    session.commit()
    with get_engine("student").begin() as conn:
        conn.execute(sa.text("INSERT INTO app.note(user_id,node_id,body) VALUES(2,'P1-WB29V3','restricted write')"))
        assert conn.execute(sa.text("SELECT body FROM app.note WHERE user_id=2")).scalar_one() == "restricted write"
    # Reapplying grants cannot bring back the old schema-wide identity access.
    apply_grants()
    with get_engine("student").connect() as conn:
        with pytest.raises(ProgrammingError, match="permission denied"):
            conn.execute(sa.text("SELECT * FROM app.user_account"))
        conn.rollback()


def test_serving_database_url_never_falls_back_to_superuser(monkeypatch):
    from caf_db.engine import database_url
    from caf_common.settings import get_settings
    monkeypatch.setattr(get_settings(), "STUDENT_DATABASE_URL", None)
    with pytest.raises(RuntimeError, match="fallback is forbidden"):
        database_url("student")
    monkeypatch.setattr(get_settings(), "STUDENT_DATABASE_URL", str(get_engine().url))
    with pytest.raises(RuntimeError, match="must authenticate"):
        database_url("student")


def test_every_application_api_requires_authentication():
    import re
    from fastapi.testclient import TestClient
    from caf_api.main import app
    client = TestClient(app)
    checked = 0
    for route_path, methods in app.openapi()["paths"].items():
        if not route_path.startswith("/api/v1/") or route_path == "/api/v1/health":
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        for method in methods:
            response = client.request(method, path)
            assert response.status_code == 401, (method, path, response.status_code, response.text)
            checked += 1
    assert checked >= 30


def test_every_administrative_api_denies_student(authenticated_client):
    import re
    from caf_api.main import app
    client = authenticated_client()
    checked = 0
    for route_path, methods in app.openapi()["paths"].items():
        admin = route_path.startswith(("/api/v1/admin/", "/api/v1/system/")) or (
            route_path.startswith("/api/v1/curate/") and "/queue" not in route_path and "/decision" not in route_path
        )
        if not admin:
            continue
        path = re.sub(r"\{[^}]+\}", "1", route_path)
        for method in methods:
            response = client.request(method, path)
            assert response.status_code == 403, (method, path, response.status_code, response.text)
            checked += 1
    assert checked >= 10


def test_stale_account_hint_rejects_reads_and_writes_without_selecting_owner(authenticated_client, session):
    from caf_db.models.app import Note
    a = authenticated_client(1)
    b = authenticated_client(2)
    b.headers['X-Expected-Account-ID'] = '1'
    assert b.get('/api/v1/subtopics/P1-WB29V3').status_code == 409
    response = b.put('/api/v1/subtopics/P1-WB29V3/notes', json={'notes': 'stale A draft'})
    assert response.status_code == 409 and response.json()['detail'] == 'identity_changed'
    assert session.get(Note, (2, 'P1-WB29V3')) is None
    a.headers['X-Expected-Account-ID'] = '2'
    assert a.get('/api/v1/me/export').status_code == 409
    b.headers['X-Expected-Account-ID'] = '2'
    assert b.get('/api/v1/me/export').json()['account_id'] == 2


def test_small_positive_budget_survives_database_round_trip(authenticated_client):
    client = authenticated_client()
    settings = client.get('/api/v1/me/settings').json()
    for key in ('groups', 'available_papers', 'available_attempts'):
        settings.pop(key)
    settings['hours_per_week'] = 0.01
    assert client.put('/api/v1/me/settings', json=settings).status_code == 200
    assert client.get('/api/v1/me/settings').json()['hours_per_week'] == 0.01
    assert client.get('/api/v1/plan').status_code == 200


@pytest.mark.parametrize('path', ['/auth/login?invitation=PRIVATE', '/auth/callback?code=PRIVATE&state=PRIVATE'])
def test_access_logging_redacts_auth_query_credentials(path):
    import logging
    from caf_api.security_logging import AUTH_ACCESS_FILTER
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d',
                               ('local', 'GET', path, '1.1', 302), None)
    assert AUTH_ACCESS_FILTER.filter(record)
    assert 'PRIVATE' not in record.getMessage()
    assert path.partition('?')[0] in record.getMessage()
