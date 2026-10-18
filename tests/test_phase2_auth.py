"""Harness-owned OIDC transport uses signed JWTs and disposable PostgreSQL."""

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import time
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
from joserfc import jwt
from joserfc.jwk import RSAKey
import pytest
import sqlalchemy as sa

import caf_api.auth as auth
from caf_common.settings import get_settings
from caf_db.models.app import AuthSession, Invitation, LoginTransaction, Settings, UserAccount
from caf_db.engine import get_session_factory


@pytest.fixture
def provider(monkeypatch, session):
    settings = get_settings()
    for name, value in {
        "OIDC_ISSUER": "https://provider.test/", "OIDC_CLIENT_ID": "client",
        "OIDC_CLIENT_SECRET": "secret", "OIDC_REDIRECT_URI": "http://testserver/auth/callback",
        "AUTH_LOCAL_DEVELOPMENT": True, "AUTH_PUBLIC_BASE_URL": "http://testserver",
    }.items():
        monkeypatch.setattr(settings, name, value)
    key = RSAKey.generate_key(2048, parameters={"kid": "test"})
    data = {"claims": {}, "nonce": None, "subject": "student-a", "email": "a@example.test", "verified": True, "key": key}

    def transport(request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": settings.OIDC_ISSUER,
                "authorization_endpoint": "https://provider.test/authorize", "token_endpoint": "https://provider.test/token",
                "jwks_uri": "https://provider.test/jwks", "id_token_signing_alg_values_supported": ["RS256"]})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [key.as_dict(private=False)]})
        if request.url.path == "/token":
            body = parse_qs(request.content.decode())
            assert "code_verifier" in body
            claims = {"iss": settings.OIDC_ISSUER, "sub": data["subject"], "aud": "client", "iat": int(time.time()),
                      "exp": int(time.time()) + 300, "nonce": data["nonce"], "email": data["email"], "email_verified": data["verified"]}
            claims.update(data["claims"])
            encoded = jwt.encode({"alg": "RS256", "kid": "test"}, claims, data["key"])
            return httpx.Response(200, json={"access_token": "discarded", "token_type": "Bearer", "id_token": encoded})
        raise AssertionError(request.url)

    def client_factory():
        return OAuth().register("provider", client_id="client", client_secret="secret",
            server_metadata_url="https://provider.test/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256", "transport": httpx.MockTransport(transport)})

    monkeypatch.setattr(auth, "oidc_client", client_factory)
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    yield data, client
    client.close()


def start_login(provider, invitation=None, return_to="/"):
    data, client = provider
    params = {"return_to": return_to}
    if invitation:
        params["invitation"] = invitation
    response = client.get("/auth/login", params=params, follow_redirects=False)
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    data["nonce"] = query["nonce"][0]
    return query["state"][0]


def invite_token(session, email="a@example.test", **kwargs):
    invitation, url = auth.create_invitation(session, email, **kwargs)
    session.commit()
    return invitation, parse_qs(urlsplit(url).query)["invitation"][0]


def complete(provider, state):
    return provider[1].get("/auth/callback", params={"state": state, "code": "test-code"}, follow_redirects=False)


def signed_in(provider, session, **kwargs):
    _, token = invite_token(session, **kwargs)
    state = start_login(provider, token)
    response = complete(provider, state)
    assert response.status_code == 302, response.text
    return provider[1].get("/api/v1/me").json()


def test_invited_login_defaults_and_single_use(provider, session):
    invitation, token = invite_token(session)
    state = start_login(provider, token, "/profile")
    response = complete(provider, state)
    assert response.status_code == 302 and response.headers["location"] == "/profile"
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
    me = provider[1].get("/api/v1/me").json()
    assert me["account"]["email"] == "a@example.test"
    assert me["account"]["id"] != 1 and me["capabilities"] == ["browse", "profile", "review"]
    settings = session.get(Settings, me["account"]["id"])
    assert settings.target_attempt_id == "2027-05" and settings.hours_per_week == 20
    assert settings.minutes_per_subtopic == 45 and settings.revision_intervals == [3, 7, 21, 60]
    assert len(settings.selected_paper_ids) == 6
    session.refresh(invitation)
    assert invitation.consumed_at is not None
    assert complete(provider, state).status_code == 400
    provider[0]["subject"] = "second-account"
    assert complete(provider, start_login(provider, token)).status_code == 403


@pytest.mark.parametrize("claims", [{"iss": "https://other.test/"}, {"aud": "wrong-client"}, {"exp": 1}, {"nonce": "wrong"}])
def test_invalid_signed_identity_rejected(provider, session, claims):
    _, token = invite_token(session)
    provider[0]["claims"] = claims
    response = complete(provider, start_login(provider, token))
    assert response.status_code == 400 and response.json()["detail"] == "invalid_provider_identity"
    assert session.scalar(sa.select(sa.func.count()).select_from(AuthSession)) == 0


def test_wrong_signature_rejected(provider, session):
    _, token = invite_token(session)
    provider[0]["key"] = RSAKey.generate_key(2048, parameters={"kid": "test"})
    assert complete(provider, start_login(provider, token)).status_code == 400


@pytest.mark.parametrize("kind", ["unverified", "mismatch", "expired", "revoked"])
def test_invitation_restrictions(provider, session, kind):
    invitation, token = invite_token(session)
    if kind == "unverified":
        provider[0]["verified"] = False
    elif kind == "mismatch":
        provider[0]["email"] = "other@example.test"
    elif kind == "expired":
        invitation.expires_at = auth.utcnow() - timedelta(seconds=1)
    else:
        invitation.revoked_at = auth.utcnow()
    session.commit()
    assert complete(provider, start_login(provider, token)).status_code == 403
    session.refresh(invitation)
    assert invitation.consumed_at is None


def test_no_invitation_no_automatic_email_link(provider, session):
    owner = session.get(UserAccount, 1)
    owner.email = "a@example.test"
    session.commit()
    assert complete(provider, start_login(provider)).status_code == 403
    session.refresh(owner)
    assert owner.subject is None and owner.status == "pending_binding"


def test_targeted_legacy_binding_preserves_profile(provider, session):
    old = session.get(Settings, 1)
    old.hours_per_week = 13
    session.commit()
    me = signed_in(provider, session, target_user_id=1, role="administrator")
    assert me["account"]["id"] == 1 and me["account"]["role"] == "administrator"
    session.refresh(old)
    assert old.hours_per_week == 13 and old.target_attempt_id == "2026-05"


def test_state_cookie_expiry_and_replay(provider, session):
    state = start_login(provider)
    assert complete(provider, "wrong").status_code == 400
    tx = session.get(LoginTransaction, auth.hash_token(state))
    tx.expires_at = auth.utcnow() - timedelta(seconds=1)
    session.commit()
    assert complete(provider, state).status_code == 400
    state = start_login(provider)
    provider[1].cookies.delete(auth.LOGIN_COOKIE)
    assert complete(provider, state).status_code == 400


@pytest.mark.parametrize("destination", ["https://evil.test/", "//evil.test/", "/%2f%2fevil.test", "/\\evil.test", "/auth/login"])
def test_return_destination_rejected(provider, destination):
    assert provider[1].get("/auth/login", params={"return_to": destination}, follow_redirects=False).status_code == 400


def test_csrf_logout_revocation_and_session_expiry(provider, session):
    me = signed_in(provider, session)
    client = provider[1]
    assert client.post("/auth/logout").status_code == 403
    headers = {"Origin": "http://testserver", "X-CSRF-Token": me["csrf_token"]}
    assert client.post("/auth/logout", headers={**headers, "Origin": "https://evil.test"}).status_code == 403
    old = client.cookies.get(auth.SESSION_COOKIE)
    assert client.post("/auth/logout", headers=headers).status_code == 204
    client.cookies.set(auth.SESSION_COOKIE, old)
    assert client.get("/api/v1/me").status_code == 401
    # Existing issuer/subject may sign in without reusing an invitation.
    client.cookies.clear()
    assert complete(provider, start_login(provider)).status_code == 302
    row = session.get(AuthSession, auth.hash_token(client.cookies.get(auth.SESSION_COOKIE)))
    row.last_seen_at = auth.utcnow() - timedelta(hours=24, seconds=1)
    session.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_admin_disable_and_student_boundary(provider, session):
    me = signed_in(provider, session)
    client = provider[1]
    assert client.get("/api/v1/admin/accounts").status_code == 403
    owner = session.get(UserAccount, 1)
    owner.issuer, owner.subject, owner.status, owner.role = "https://provider.test/", "admin", "active", "administrator"
    session.commit()
    token, admin_session = auth.create_session(session, 1)
    session.commit()
    client.cookies.clear()
    client.cookies.set(auth.SESSION_COOKIE, token)
    headers = {"Origin": "http://testserver", "X-CSRF-Token": admin_session.csrf_token}
    assert client.patch(f'/api/v1/admin/accounts/{me["account"]["id"]}', json={"status": "disabled"}, headers=headers).status_code == 200
    sessions = session.scalars(sa.select(AuthSession).where(AuthSession.user_id == me["account"]["id"])).all()
    for item in sessions:
        session.refresh(item)
        assert item.revoked_at is not None


def test_admin_invitation_endpoints_and_rejected_role_injection(provider, session):
    me = signed_in(provider, session, target_user_id=1, role="administrator")
    client = provider[1]
    headers = {"Origin": "http://testserver", "X-CSRF-Token": me["csrf_token"]}
    assert client.post("/api/v1/admin/invitations", json={"email": "b@example.test", "role": "administrator"}, headers=headers).status_code == 422
    response = client.post("/api/v1/admin/invitations", json={"email": "b@example.test"}, headers=headers)
    assert response.status_code == 200 and response.json()["role"] == "student"
    created = response.json()
    token = parse_qs(urlsplit(created["invitation_url"]).query)["invitation"][0]
    invitation = session.get(Invitation, created["id"])
    assert invitation.token_hash == auth.hash_token(token) and invitation.token_hash != token
    assert all("token_hash" not in item for item in client.get("/api/v1/admin/invitations").json())
    assert client.post(f'/api/v1/admin/invitations/{created["id"]}/revoke', headers=headers).status_code == 200
    session.refresh(invitation)
    assert invitation.revoked_at is not None


def test_bootstrap_cli_and_recovered_credential_revocation(provider, session):
    from typer.testing import CliRunner
    from caf_cli.auth import app
    runner = CliRunner()
    response = runner.invoke(app, ["bootstrap", "--user-id", "1", "--email", "owner@example.test"])
    assert response.exit_code == 0, response.output
    invitation = session.scalar(sa.select(Invitation).where(Invitation.target_user_id == 1))
    assert invitation.role == "administrator" and invitation.email == "owner@example.test"
    assert session.get(UserAccount, 1).status == "pending_binding"
    assert runner.invoke(app, ["bootstrap", "--user-id", "1", "--email", "different@example.test"]).exit_code != 0
    token, row = auth.create_session(session, 1)
    session.commit()
    state = start_login(provider)
    revoked = runner.invoke(app, ["revoke-restored-credentials"])
    assert revoked.exit_code == 0, revoked.output
    session.refresh(row)
    session.refresh(invitation)
    assert row.revoked_at is not None and invitation.revoked_at is not None
    session.expire_all()
    assert session.get(LoginTransaction, auth.hash_token(state)).consumed_at is not None


def test_production_auth_configuration_required(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.app, "env", "production")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", "")
    with pytest.raises(RuntimeError, match="Production requires"):
        auth.validate_auth_configuration()


def test_concurrent_invitation_redemption_is_atomic(provider, session):
    invitation, _ = invite_token(session)

    def redeem(subject):
        from fastapi import HTTPException
        with get_session_factory("identity")() as db:
            try:
                account = auth.bind_identity(db, {"iss": "https://provider.test/", "sub": subject,
                    "email": "a@example.test", "email_verified": True}, invitation.token_hash)
                db.commit()
                return account.id
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(redeem, ["one", "two"]))
    assert results.count(403) == 1
    assert session.scalar(sa.select(sa.func.count()).select_from(UserAccount).where(UserAccount.issuer == "https://provider.test/")) == 1


def test_absolute_expiry_and_session_rotation(provider, session):
    me = signed_in(provider, session)
    client = provider[1]
    old = client.cookies.get(auth.SESSION_COOKIE)
    assert complete(provider, start_login(provider)).status_code == 302
    assert client.cookies.get(auth.SESSION_COOKIE) != old
    old_session = session.get(AuthSession, auth.hash_token(old))
    assert old_session.revoked_at is not None
    current = session.get(AuthSession, auth.hash_token(client.cookies.get(auth.SESSION_COOKIE)))
    current.expires_at = auth.utcnow() - timedelta(seconds=1)
    session.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_legacy_migration_preserves_all_personal_rows_and_large_ids(isolated_database):
    from uuid import uuid4
    from alembic import command
    from alembic.config import Config
    database = f"caf_identity_baseline_{uuid4().hex}"
    isolated_database.allow(database)
    admin = sa.create_engine(isolated_database.url(), isolation_level="AUTOCOMMIT")
    engine = sa.create_engine(isolated_database.url(database))
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{database}"'))
        with engine.begin() as conn:
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "0002_score_config_snapshot")
            statements = [
                "INSERT INTO ref.attempt(id,exam_year,exam_month,label,verified) VALUES('2026-05',2026,5,'May 2026',false)",
                "INSERT INTO ref.scheme(id,name) VALUES('scheme','Scheme')",
                "INSERT INTO ref.paper(id,scheme_id,code,name,max_marks,is_current) VALUES('paper','scheme','P1','Paper',100,true)",
                "INSERT INTO ref.node(id,paper_id,level,name,seq,status) VALUES('chapter','paper','chapter','Chapter',1,'active')",
                "INSERT INTO ref.node(id,paper_id,parent_id,level,name,seq,status) VALUES('subtopic','paper','chapter','subtopic','Subtopic',1,'active')",
                "INSERT INTO app.user_account(id,name) VALUES(32767,'Existing owner')",
                "INSERT INTO app.settings(user_id,target_attempt_id,hours_per_week,minutes_per_subtopic,revision_intervals) VALUES(32767,'2026-05',13,27,ARRAY[2,9])",
                "INSERT INTO app.note(user_id,node_id,body) VALUES(32767,'subtopic','Keep my note')",
                "INSERT INTO app.progress(user_id,node_id,status,verify_flag) VALUES(32767,'subtopic','done',true)",
                "INSERT INTO app.progress_event(user_id,node_id,to_status) VALUES(32767,'subtopic','done')",
                "INSERT INTO app.revision_event(user_id,node_id,outcome) VALUES(32767,'subtopic','shaky')",
                "INSERT INTO app.mock_test(user_id,paper_id,score,max_score,taken_on) VALUES(32767,'paper',70,100,'2026-01-01')",
                "INSERT INTO app.study_session(user_id,node_id,started_at,minutes) VALUES(32767,'subtopic',now(),17)",
                "INSERT INTO core.decision(unit_fingerprint,action,payload,blind) VALUES('fingerprint','accept','{}',false)",
            ]
            for statement in statements:
                conn.execute(sa.text(statement))
            tables = ["app.user_account", "app.settings", "app.note", "app.progress", "app.progress_event", "app.revision_event", "app.mock_test", "app.study_session", "core.decision"]
            columns, original = {}, {}
            for table in tables:
                result = conn.execute(sa.text(f"SELECT * FROM {table}"))
                columns[table] = ",".join(result.keys())
                original[table] = result.all()
            command.upgrade(cfg, "head")
            for table in tables:
                assert conn.execute(sa.text(f"SELECT {columns[table]} FROM {table}")).all() == original[table]
            assert conn.execute(sa.text("SELECT status FROM app.user_account WHERE id=32767")).scalar_one() == "pending_binding"
            assert conn.execute(sa.text("SELECT actor_id FROM core.decision")).scalar_one() is None
            assert conn.execute(sa.text("INSERT INTO app.user_account(name) VALUES('New owner') RETURNING id")).scalar_one() == 32768
            assert conn.execute(sa.text("SELECT verified,exam_start_date FROM ref.attempt WHERE id='2027-05'")).one() == (False, None)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE "{database}"'))
        admin.dispose()


@pytest.mark.parametrize("failure", ["dns", "timeout", "http_status"])
def test_provider_discovery_failure_is_unavailable_without_login_transaction(provider, session, monkeypatch, failure):
    from caf_api.main import authentication_error
    from starlette.exceptions import HTTPException as StarletteHTTPException

    client = provider[1]
    client.app.add_exception_handler(StarletteHTTPException, authentication_error)
    oauth = auth.oidc_client()

    def unavailable(request):
        if failure == "dns":
            raise httpx.ConnectError("Hostname resolution failed", request=request)
        if failure == "timeout":
            raise httpx.ConnectTimeout("Provider timed out", request=request)
        return httpx.Response(503, json={"error": "unavailable"})

    oauth.client_kwargs["transport"] = httpx.MockTransport(unavailable)
    monkeypatch.setattr(auth, "oidc_client", lambda: oauth)
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 503
    assert response.json() == {"detail": "identity_provider_unavailable"}
    assert not response.headers.get("set-cookie")
    assert session.scalar(sa.select(sa.func.count()).select_from(LoginTransaction)) == 0

    response = client.get("/auth/login", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 503
    assert "Sign-in unavailable" in response.text
    assert "internet connection and DNS" in response.text
    assert "Internal Server Error" not in response.text
