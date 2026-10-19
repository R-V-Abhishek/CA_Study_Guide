"""Invitation-bound OIDC identity and revocable, opaque application sessions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from urllib.parse import urlencode, urlsplit
from typing import Literal

from authlib.integrations.starlette_client import OAuth
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.app import AuthSession, Invitation, LoginTransaction, Settings, UserAccount
from caf_db.models.ref import Paper

router = APIRouter(tags=["identity"])
SESSION_COOKIE = "caf_session"
LOGIN_COOKIE = "caf_login"
logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_identity_db():
    with get_session_factory("identity")() as db:
        yield db


def validate_auth_configuration() -> None:
    settings = get_settings()
    values = (settings.OIDC_ISSUER, settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET, settings.OIDC_REDIRECT_URI)
    if settings.app.env not in ("development", "test") and not all(values):
        raise RuntimeError("Production requires OIDC issuer, client ID, client secret, and redirect URI")
    if settings.AUTH_LOCAL_DEVELOPMENT and settings.app.env not in ("development", "test"):
        raise RuntimeError("Insecure auth cookies are restricted to explicit local development")
    if all(values) and not settings.AUTH_LOCAL_DEVELOPMENT:
        for value in (settings.OIDC_ISSUER, settings.OIDC_REDIRECT_URI, settings.AUTH_PUBLIC_BASE_URL):
            if urlsplit(value).scheme != "https":
                raise RuntimeError("OIDC and application URLs must use HTTPS outside local development")


def allowed_origins() -> set[str]:
    settings = get_settings()
    base = urlsplit(settings.AUTH_PUBLIC_BASE_URL)
    origins = {f"{base.scheme}://{base.netloc}"}
    if settings.app.env in ("development", "test"):
        origins.update(item.strip().rstrip("/") for item in settings.AUTH_ALLOWED_ORIGINS.split(",") if item.strip())
    return origins


@dataclass(frozen=True)
class Principal:
    id: int
    name: str
    email: str | None
    role: str
    status: str


def require_account(request: Request) -> Principal:
    if "account" in request.scope.get("state", {}):
        return request.state.account
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "session_expired")
    now = utcnow()
    with get_session_factory("identity")() as db:
        session = db.get(AuthSession, hash_token(token))
        if session is None or session.revoked_at is not None or session.expires_at <= now or session.last_seen_at <= now - timedelta(hours=24):
            raise HTTPException(401, "session_expired")
        account = db.get(UserAccount, session.user_id)
        if account is None or account.status != "active":
            raise HTTPException(403, "account_disabled" if account and account.status == "disabled" else "invite_required")
        expected_account = request.headers.get("x-expected-account-id")
        if expected_account is not None and expected_account != str(account.id):
            # A stale tab may send a request after another tab rotates the
            # shared cookie. This header rejects stale context, never sets owner.
            raise HTTPException(409, "identity_changed")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.headers.get("x-csrf-token", "")
            if request.headers.get("origin") not in allowed_origins() or not secrets.compare_digest(supplied.encode(), session.csrf_token.encode()):
                raise HTTPException(403, "csrf_rejected")
        principal = Principal(account.id, account.name, account.email, account.role, account.status)
        session.last_seen_at = now
        db.commit()
        request.state.account = principal
        request.state.csrf_token = session.csrf_token
        return principal


def require_admin(request: Request) -> Principal:
    principal = require_account(request)
    if principal.role != "administrator":
        raise HTTPException(403, "administrator_required")
    return principal


def create_session(db: Session, user_id: int) -> tuple[str, AuthSession]:
    """Return cookie token and persisted session; callers commit the transaction."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    session = AuthSession(token_hash=hash_token(token), user_id=user_id,
                          csrf_token=secrets.token_urlsafe(32), created_at=now,
                          expires_at=now + timedelta(days=7), last_seen_at=now)
    db.add(session)
    db.flush()
    return token, session


def set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=not get_settings().AUTH_LOCAL_DEVELOPMENT, samesite="lax", path="/")


def local_return_to(path: str) -> str:
    decoded = path
    from urllib.parse import unquote
    for _ in range(3):
        decoded = unquote(decoded)
    if not decoded.startswith("/") or decoded.startswith("//") or "\\" in decoded or any(ord(char) < 32 for char in decoded):
        raise HTTPException(400, "invalid_return_destination")
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/auth/"):
        raise HTTPException(400, "invalid_return_destination")
    return path


def oidc_client():
    settings = get_settings()
    if not all((settings.OIDC_ISSUER, settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET, settings.OIDC_REDIRECT_URI)):
        raise HTTPException(503, "authentication_not_configured")
    oauth = OAuth()
    return oauth.register("provider", client_id=settings.OIDC_CLIENT_ID,
                          client_secret=settings.OIDC_CLIENT_SECRET,
                          server_metadata_url=settings.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration",
                          client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"})


@router.get("/auth/login")
async def login(return_to: str = "/", invitation: str | None = None, db: Session = Depends(get_identity_db)):
    return_to = local_return_to(return_to)
    client = oidc_client()
    try:
        metadata = await client.load_server_metadata()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("OIDC discovery unavailable: provider=%s failure=%s",
                       urlsplit(get_settings().OIDC_ISSUER).hostname, type(exc).__name__)
        raise HTTPException(503, "identity_provider_unavailable") from exc
    if metadata.get("issuer") != get_settings().OIDC_ISSUER:
        raise HTTPException(400, "invalid_identity_provider")
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    authorization = await client.create_authorization_url(get_settings().OIDC_REDIRECT_URI, state=state, nonce=nonce, code_verifier=verifier)
    db.add(LoginTransaction(state_hash=hash_token(state), browser_hash=hash_token(browser),
                            nonce=nonce, code_verifier=verifier,
                            invitation_hash=hash_token(invitation) if invitation else None,
                            return_to=return_to, expires_at=utcnow() + timedelta(minutes=10)))
    db.commit()
    response = RedirectResponse(authorization["url"], status_code=302)
    set_cookie(response, LOGIN_COOKIE, browser, 600)
    return response


def bind_identity(db: Session, identity: dict, invitation_hash: str | None) -> UserAccount:
    """Issuer/subject lookup never links an existing account by email."""
    issuer, subject = identity["iss"], identity["sub"]
    account = db.scalar(sa.select(UserAccount).where(UserAccount.issuer == issuer, UserAccount.subject == subject).with_for_update())
    if account is not None:
        if account.status != "active":
            raise HTTPException(403, "account_disabled")
        return account
    if not invitation_hash:
        raise HTTPException(403, "invite_required")
    invitation = db.scalar(sa.select(Invitation).where(Invitation.token_hash == invitation_hash).with_for_update())
    now = utcnow()
    if invitation is None or invitation.revoked_at is not None or invitation.consumed_at is not None or invitation.expires_at <= now:
        raise HTTPException(403, "invitation_invalid")
    email = identity.get("email")
    if identity.get("email_verified") is not True or not email or email.casefold() != invitation.email.casefold():
        raise HTTPException(403, "invitation_email_mismatch")
    if invitation.target_user_id is not None:
        account = db.scalar(sa.select(UserAccount).where(UserAccount.id == invitation.target_user_id).with_for_update())
        if account is None or account.status != "pending_binding" or account.subject is not None:
            raise HTTPException(409, "account_already_bound")
    else:
        account = UserAccount(name=identity.get("name") or email)
        db.add(account)
    account.issuer, account.subject = issuer, subject
    account.email, account.email_verified = email, True
    account.role, account.status = invitation.role, "active"
    db.flush()
    if db.get(Settings, account.id) is None:
        papers = list(db.scalars(sa.select(Paper.id).where(Paper.is_current.is_(True)).order_by(Paper.id)))
        db.add(Settings(user_id=account.id, target_attempt_id="2027-05", selected_paper_ids=papers,
                        hours_per_week=20, minutes_per_subtopic=45, revision_intervals=[3, 7, 21, 60]))
    invitation.consumed_at = now
    return account


@router.get("/auth/callback")
async def callback(request: Request, state: str = "", code: str = "", db: Session = Depends(get_identity_db)):
    browser = request.cookies.get(LOGIN_COOKIE, "")
    tx = db.scalar(sa.select(LoginTransaction).where(LoginTransaction.state_hash == hash_token(state)).with_for_update())
    if not state or not browser or tx is None or tx.consumed_at is not None or tx.expires_at <= utcnow() or not secrets.compare_digest(tx.browser_hash, hash_token(browser)):
        raise HTTPException(400, "invalid_login_transaction")
    tx.consumed_at = utcnow()
    db.commit()  # A failed provider exchange also consumes the one-time transaction.
    if not code:
        raise HTTPException(400, "invalid_provider_response")
    try:
        client = oidc_client()
        metadata = await client.load_server_metadata()
        if metadata.get("issuer") != get_settings().OIDC_ISSUER:
            raise ValueError("Provider issuer mismatch")
        token = await client.fetch_access_token(code=code, redirect_uri=get_settings().OIDC_REDIRECT_URI, code_verifier=tx.code_verifier)
        identity = await client.parse_id_token(token, nonce=tx.nonce, leeway=0,
            claims_options={"iss": {"essential": True, "value": get_settings().OIDC_ISSUER},
                            "sub": {"essential": True}, "exp": {"essential": True},
                            "aud": {"essential": True}})
        if identity.get("nonce") != tx.nonce or identity.get("iss") != get_settings().OIDC_ISSUER:
            raise ValueError("Identity nonce/issuer mismatch")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "invalid_provider_identity") from exc
    try:
        account = bind_identity(db, dict(identity), tx.invitation_hash)
    except IntegrityError as exc:
        # Distinct invitations may race to bind the same issuer/subject.
        db.rollback()
        raise HTTPException(409, "identity_already_bound") from exc
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        old_session = db.get(AuthSession, hash_token(old_token))
        if old_session is not None:
            old_session.revoked_at = utcnow()
    session_token, _ = create_session(db, account.id)
    db.commit()
    response = RedirectResponse(local_return_to(tx.return_to), status_code=302)
    response.delete_cookie(LOGIN_COOKIE, path="/")
    set_cookie(response, SESSION_COOKIE, session_token, 7 * 86400)
    return response


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str | None
    role: str
    status: str


class MeResponse(BaseModel):
    account: AccountResponse
    capabilities: list[str]
    csrf_token: str


@router.get("/api/v1/me", response_model=MeResponse)
def me(request: Request, account: Principal = Depends(require_account)):
    return MeResponse(account=AccountResponse.model_validate(account),
                      capabilities=["browse", "profile", "review"] + (["admin"] if account.role == "administrator" else []),
                      csrf_token=request.state.csrf_token)


@router.post("/auth/logout")
def logout(request: Request, account: Principal = Depends(require_account), db: Session = Depends(get_identity_db)):
    session = db.get(AuthSession, hash_token(request.cookies[SESSION_COOKIE]))
    session.revoked_at = utcnow()
    db.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(LOGIN_COOKIE, path="/")
    return response


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    expires_at: datetime
    consumed_at: datetime | None
    revoked_at: datetime | None
    target_user_id: int | None


class CreatedInvitationResponse(InvitationResponse):
    invitation_url: str


def create_invitation(db: Session, email: str, *, created_by: int | None = None,
                      target_user_id: int | None = None, role: str = "student") -> tuple[Invitation, str]:
    token = secrets.token_urlsafe(32)
    invitation = Invitation(token_hash=hash_token(token), email=email.strip().casefold(), role=role,
                            target_user_id=target_user_id, created_by=created_by,
                            expires_at=utcnow() + timedelta(days=7))
    db.add(invitation)
    db.flush()
    url = get_settings().AUTH_PUBLIC_BASE_URL.rstrip("/") + "/auth/login?" + urlencode({"invitation": token})
    return invitation, url


@router.get("/api/v1/admin/invitations", response_model=list[InvitationResponse])
def invitations(admin: Principal = Depends(require_admin), db: Session = Depends(get_identity_db)):
    return db.scalars(sa.select(Invitation).order_by(Invitation.id.desc())).all()


@router.post("/api/v1/admin/invitations", response_model=CreatedInvitationResponse)
def invite(body: InvitationRequest, admin: Principal = Depends(require_admin), db: Session = Depends(get_identity_db)):
    invitation, url = create_invitation(db, body.email, created_by=admin.id)
    db.commit()
    return CreatedInvitationResponse(**InvitationResponse.model_validate(invitation).model_dump(), invitation_url=url)


@router.post("/api/v1/admin/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: int, admin: Principal = Depends(require_admin), db: Session = Depends(get_identity_db)):
    invitation = db.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(404, "invitation_not_found")
    invitation.revoked_at = utcnow()
    db.commit()
    return {"status": "revoked"}


@router.get("/api/v1/admin/accounts", response_model=list[AccountResponse])
def accounts(admin: Principal = Depends(require_admin), db: Session = Depends(get_identity_db)):
    return db.scalars(sa.select(UserAccount).order_by(UserAccount.id)).all()


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["student", "administrator"] | None = None
    status: Literal["active", "disabled"] | None = None


@router.patch("/api/v1/admin/accounts/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, body: AccountUpdate, admin: Principal = Depends(require_admin), db: Session = Depends(get_identity_db)):
    account = db.scalar(sa.select(UserAccount).where(UserAccount.id == account_id).with_for_update())
    if account is None:
        raise HTTPException(404, "account_not_found")
    if account.status == "pending_binding":
        raise HTTPException(409, "account_requires_explicit_binding")
    if body.role is not None:
        account.role = body.role
    if body.status is not None:
        account.status = body.status
    if body.status == "disabled":
        db.execute(sa.update(AuthSession).where(AuthSession.user_id == account.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return account
