# Phase 2 setup and recovery

Both applications use one backend cookie session. Credentials and provider tokens
never enter browser storage. Students must redeem an invitation with the same
verified email. An Auth0 registration alone provides no application access.

## Auth0 setup

1. Create an Auth0 tenant and a **Regular Web Application**.
2. In its settings, use these local development values:
   - Allowed Callback URLs: `http://localhost:8000/auth/callback`
   - Allowed Logout URLs: `http://localhost:8000`
   - Allowed Web Origins: `http://localhost:8000`
3. Keep OIDC conformance and RS256 signing enabled. Enable Authorization Code grant.
4. In the ignored local `.env`, fill:
   ```dotenv
   OIDC_ISSUER=https://YOUR-TENANT.REGION.auth0.com/
   OIDC_CLIENT_ID=YOUR_CLIENT_ID
   OIDC_CLIENT_SECRET=YOUR_CLIENT_SECRET
   OIDC_REDIRECT_URI=http://localhost:8000/auth/callback
   AUTH_PUBLIC_BASE_URL=http://localhost:8000
   AUTH_LOCAL_DEVELOPMENT=true
   ```
   The issuer must equal discovery's issuer, including its trailing slash.
   Keep the client secret in `.env`; do not send or commit it.
5. Create/use a login identity in that tenant and verify its email. The bootstrap
   invitation must name that email. Application sessions expire after seven days
   or 24 hours idle. Logout revokes the application session; the provider's own
   SSO session follows Auth0 configuration.

[Auth0 application settings](https://auth0.com/docs/get-started/applications/application-settings)
and [Authlib OIDC integration](https://docs.authlib.org/en/v1.5.2/client/starlette.html)
provide the provider-side details.

## Database and owner binding

Existing migrations are frozen. `0003_identity` widens preserved owner IDs,
marks unbound owners `pending_binding`, adds identity tables and actor references,
and creates an unverified May 2027 planning target without an exam date.

Create and verify a checkpoint before migrating an existing installation:

```sh
uv run caf backup run
uv run caf backup verify --dump-file PATH_TO_CHECKPOINT_DUMP
uv run scripts/phase2_migration_drill.py PATH_TO_CHECKPOINT_MANIFEST
uv run caf db migrate
uv run caf db configure-connections
uv run caf db grants
uv run caf auth bootstrap --user-id EXISTING_OWNER_ID --email VERIFIED_OWNER_EMAIL
```

An older installation needs `caf db configure-connections` and `caf db grants`
**before** using the new backup command: backup dumps now authenticate with the
read-only backup role. These commands add missing credentials and URLs, preserve
existing settings, and revoke legacy broad grants. The backup role can read
legacy tables before migration. Initial setup also configures named connections.

Bootstrap prints a single-use copyable invitation; its raw token is not stored in
the database. Open it in the same browser that performs hosted sign-in. Bootstrap
requires an explicitly nominated unbound owner; it never chooses the first login.
Existing owner settings and records remain attached to the original ID. Invitations
expire after seven days; create a new one if provider setup takes longer.

The application exposes invitation and account administration in `/curator/accounts`
for active administrators. Students can use classification review and shared
content, and `/profile` for settings and a private JSON export. Administrative
recomputation requires a specific attempt. Selecting an attempt without a matching
successful non-shadow score run preserves personal progress and shows unavailable
scores and an empty plan with a reason. Settings changes do not recompute scores.

## Production serving

Set `CAF_ENV=production`, `AUTH_LOCAL_DEVELOPMENT=false`, HTTPS application and
callback URLs, and the production Auth0 callback allowlist. Missing OIDC
configuration aborts production startup. Development CORS origins are ignored in
production; serve both apps and the API on the shared origin.

Use separate environment files/secrets for administration and serving. Remove
`DATABASE_URL`, `MIGRATION_DATABASE_URL`, superuser passwords, and role provisioning
passwords from the serving process. Provide the named connection URLs it needs:

| URL | Database role | Capability |
| --- | --- | --- |
| `STUDENT_DATABASE_URL` | `caf_app` | Shared reads, personal study writes |
| `IDENTITY_DATABASE_URL` | `caf_identity` | Accounts, settings, invitations, logins, sessions |
| `CURATION_DATABASE_URL` | `caf_curator` | Shared review, decisions, publication, unit classification status |
| `OPERATIONS_DATABASE_URL` | `caf_operations` | Shared corpus, scoring, operational events; no private profiles |
| `BACKUP_DATABASE_URL` | `caf_backup` | Full read-only dump, including identity sequences |
| `PIPELINE_DATABASE_URL` | `caf_pipeline` | Acquisition worker reads/writes |

Named pools reject administrative usernames, superuser/role/database creation
privileges, and absent URLs. They never fall back to migration credentials.
Ownership remains in explicit application queries; PostgreSQL grants enforce
capabilities, not per-account row policies. CLI personal commands require
`--user-id`; scoring requires `--target-attempt`.

## Recovery reopening

Keep the recovered server closed to traffic. Restore all database tables and
source/config artifacts, provision restricted roles using the administration
environment, and then invalidate restored credentials:

```sh
uv run caf auth revoke-restored-credentials
```

This revokes all restored sessions, pending login transactions, and unconsumed
invitations. Reissue needed invitations afterwards, then reopen the deployment.
This prevents a restore from reviving a previously logged-out session or invitation.
The new authentication tables are included in the full dump and manifest.

## Local verification

```sh
uv run pytest -q
uv run scripts/export_openapi.py
pnpm --dir web/packages/api-client generate
pnpm --dir web type-check
pnpm --dir web build
pnpm --dir web test:browser
```

The browser runner owns a disposable PostgreSQL database and an RSA-signing OIDC
provider with PKCE checks. Its fixture/session endpoints belong exclusively to
`scripts/browser_server.py`, not the production application. Test-provider results
do not verify a real Auth0 tenant. Real-provider acceptance and native Windows
verification remain separate gates.

The local real-provider flow passed on 2026-10-02, including explicit legacy-owner
binding, returning sign-in and logout across both apps. See
[the verification report](Phase2_Verification.md). Production URLs and native
Windows still require their own verification.
