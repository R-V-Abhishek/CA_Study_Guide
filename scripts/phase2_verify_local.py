"""Read-only serving and grant evidence from the normal local installation."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

from caf_api.main import app
from caf_common.settings import get_settings
from caf_db.engine import get_engine

roles = {}
for operation in ('student', 'identity', 'curation', 'operations', 'backup', 'pipeline'):
    with get_engine(operation).connect() as connection:
        row = connection.execute(sa.text("SELECT current_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert not any(row[1:])
        roles[operation] = {'role': row[0], 'administrative': False}

denials = {}
for operation, table in (('student','app.auth_session'), ('student','app.user_account'),
                         ('curation','app.note'), ('operations','app.note'), ('identity','app.note')):
    with get_engine(operation).connect() as connection:
        try:
            connection.execute(sa.text(f'SELECT * FROM {table} LIMIT 1'))
        except ProgrammingError as exc:
            assert exc.orig.sqlstate == '42501'
            denials[f'{operation}:{table}'] = 'permission_denied'
            connection.rollback()
        else:
            raise AssertionError(f'{operation} unexpectedly reads {table}')
with get_engine('identity').connect() as connection:
    owners = [dict(row) for row in connection.execute(sa.text('SELECT id,status,role FROM app.user_account ORDER BY id')).mappings()]
    bindings = [dict(row) for row in connection.execute(sa.text('SELECT target_user_id,role,consumed_at IS NULL AS unconsumed FROM app.invitation WHERE revoked_at IS NULL')).mappings()]
with TestClient(app) as client:
    assert client.get('/api/v1/health').status_code == 200
    statuses = {path: client.get(path).status_code for path in ('/api/v1/me', '/api/v1/dashboard', '/api/v1/me/export', '/api/v1/curate/queue', '/api/v1/system/backups')}
    assert set(statuses.values()) == {401}
    if not get_settings().OIDC_CLIENT_SECRET:
        assert client.get('/auth/login').status_code == 503
    assert client.get('/profile').status_code == 200
    assert client.get('/curator/accounts').status_code == 200
    assert client.get('/api/v1/me').headers['cache-control'] == 'no-store'
Path('docs/Phase2_Local_Verification.json').write_text(json.dumps({'roles': roles, 'denied_reads': denials, 'owners': owners,
    'pending_bindings': bindings, 'unauthenticated_statuses': statuses, 'static_routes': 'passed',
    'real_auth0_configured': bool(get_settings().OIDC_CLIENT_SECRET),
    'real_provider_evidence': 'Phase2_Auth0_Verification.json'}, indent=2, default=str) + '\n')
print('Local restricted connections and protected routes passed; real-provider evidence is recorded separately.')
