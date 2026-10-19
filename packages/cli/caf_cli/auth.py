"""Explicit legacy-owner binding and recovered-credential revocation."""

from rich.console import Console
import sqlalchemy as sa
import typer

from caf_db.engine import get_session_factory
from caf_db.models.app import AuthSession, Invitation, LoginTransaction, UserAccount
from caf_api.auth import InvitationRequest, create_invitation, utcnow

app = typer.Typer(help="Invitation-bound account administration")
console = Console()


@app.command("bootstrap")
def bootstrap(user_id: int = typer.Option(..., "--user-id", help="Existing unbound owner ID to preserve"),
              email: str = typer.Option(..., "--email", help="Intended administrator's verified provider email")) -> None:
    """Create a targeted administrator invitation; never bind an arbitrary login."""
    email = InvitationRequest(email=email).email
    with get_session_factory("identity")() as db:
        account = db.scalar(sa.select(UserAccount).where(UserAccount.id == user_id).with_for_update())
        if account is None or account.status != "pending_binding" or account.subject is not None:
            raise typer.BadParameter("Target account must exist and remain pending_binding")
        active = db.scalar(sa.select(Invitation.id).where(
            Invitation.target_user_id == user_id, Invitation.revoked_at.is_(None),
            Invitation.consumed_at.is_(None), Invitation.expires_at > utcnow()))
        if active is not None:
            raise typer.BadParameter("Target account already has a live binding invitation; revoke it before replacing")
        _, url = create_invitation(db, email, target_user_id=user_id, role="administrator")
        db.commit()
    console.print(f"Administrator binding invitation for account {user_id}:")
    console.print(url, soft_wrap=True, markup=False)


@app.command("revoke-restored-credentials")
def revoke_restored_credentials() -> None:
    """Invalidate restored sessions, pending logins and unconsumed invitations."""
    now = utcnow()
    with get_session_factory("identity")() as db:
        sessions = db.execute(sa.update(AuthSession).where(AuthSession.revoked_at.is_(None)).values(revoked_at=now)).rowcount
        logins = db.execute(sa.update(LoginTransaction).where(LoginTransaction.consumed_at.is_(None)).values(consumed_at=now)).rowcount
        invitations = db.execute(sa.update(Invitation).where(Invitation.consumed_at.is_(None), Invitation.revoked_at.is_(None)).values(revoked_at=now)).rowcount
        db.commit()
    console.print(f"Revoked {sessions} sessions, {logins} login transactions, {invitations} pending invitations.")
