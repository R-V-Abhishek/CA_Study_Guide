"""Record real-provider binding/session evidence without exporting credentials."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import sqlalchemy as sa
import typer

from caf_common.settings import get_settings
from caf_db.engine import get_engine


def main(user_id: int = typer.Option(...), email: str = typer.Option(...),
         logged_out: bool = typer.Option(False)):
    now = datetime.now(timezone.utc)
    with get_engine('identity').connect() as connection:
        account = connection.execute(sa.text('SELECT id,status,role,issuer,subject,email,email_verified FROM app.user_account WHERE id=:id'), {'id': user_id}).mappings().one()
        assert account['status'] == 'active' and account['role'] == 'administrator'
        assert account['issuer'] == get_settings().OIDC_ISSUER and account['subject']
        assert account['email_verified'] and account['email'].casefold() == email.casefold()
        assert connection.scalar(sa.text('SELECT count(*) FROM app.invitation WHERE target_user_id=:id AND consumed_at IS NOT NULL'), {'id': user_id}) == 1
        active = connection.scalar(sa.text('SELECT count(*) FROM app.auth_session WHERE user_id=:id AND revoked_at IS NULL AND expires_at>:now AND last_seen_at>:idle'), {'id': user_id, 'now': now, 'idle': now - timedelta(hours=24)})
        revoked = connection.scalar(sa.text('SELECT count(*) FROM app.auth_session WHERE user_id=:id AND revoked_at IS NOT NULL'), {'id': user_id})
        if logged_out:
            assert active == 0 and revoked >= 1
        else:
            assert active >= 1
    path = Path('docs/Phase2_Auth0_Verification.json')
    evidence = json.loads(path.read_text()) if path.exists() else {}
    evidence['logout' if logged_out else 'login'] = {
        'verified_at': now.isoformat(), 'account_id': user_id,
        'configured_issuer_matches': True, 'stable_subject_bound': True,
        'nominated_email_verified': True, 'role': account['role'],
        'invitation_consumed': True, 'active_sessions': active, 'revoked_sessions': revoked,
    }
    path.write_text(json.dumps(evidence, indent=2) + '\n')
    print('Real Auth0 account binding and', 'logout revocation' if logged_out else 'active session', 'verified.')


if __name__ == '__main__':
    typer.run(main)
