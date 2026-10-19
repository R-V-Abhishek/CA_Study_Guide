# Phase 2 verification — 2026-10-02

Implementation and isolated acceptance passed on `feat/phase2-auth`, based on
Phase 1 commit `af852f4`. Real Auth0 invitation redemption, verified sign-in,
preserved owner profile access and logout also passed on the local installation.
Synthetic OIDC tests remain separate evidence. Native Windows verification remains pending.

| Check | Result |
| --- | --- |
| Full isolated Python suite, `uv run pytest -q --tb=short` | **178 passed**, 33.67 seconds |
| Final bootstrap/recovery CLI formatting regression | Passed |
| Chromium/WebKit, `pnpm --dir web test:browser` | **82 passed**, 41 per engine, 2.5 minutes |
| Applications, API client and browser fixture type checks | Passed |
| Production distributions (rebuilt by browser harness) | Both passed |
| OpenAPI and generated TypeScript | Regenerated; checked-in JSON equals `app.openapi()` |
| Pre-migration checkpoint restore | All **43 table digests** and archived files matched |
| Migration on restored checkpoint | Every original stored value preserved across **42 tables** |
| Normal database migration | Same preservation assertions passed in the committing transaction |
| Actual normal serving credentials | Six restricted roles verified non-superuser, no creation/bypass privileges |
| Normal capability denials | Student cannot read accounts/sessions; identity, curation, operations cannot read notes |
| Post-migration checkpoint restore | All **46 table digests** and archived files matched |
| Real Auth0 hosted flow | User completed Google sign-in/consent; callback bound owner ID 1; profile and logout verified |
| Diff review and whitespace | Clean; earlier migrations unchanged |

## Implemented behavior

Authlib authorization code sign-in uses database-backed state, browser binding,
nonce and PKCE. RSA signature, issuer, audience, expiry and nonce failures are
rejected. Credentials and provider tokens are absent from browser storage and
application persistence. Provider registration requires an invitation; subsequent
lookup uses issuer/subject, never email-based automatic linking.

Invitations store only token hashes, expire after seven days, and are single-use,
revocable, and verified-email bound. Login transactions expire after ten minutes
and cannot replay. Session cookies are opaque, HttpOnly, SameSite=Lax, secure unless
local development is explicitly enabled, and expire absolutely after seven days
or after 24 hours idle. Login rotates, logout revokes, and disablement revokes all
account sessions. Mutations check CSRF and Origin; production auth configuration
fails closed and development CORS does not enable arbitrary origins.

All application APIs require authentication except minimal health and login/callback
entry points. Administrator permissions cover invitations/accounts, source document
administration, bulk acceptance, recomputation, backups, operational reports and
model evaluation, including methods without database dependencies. A stale account
hint header can only reject changed identity; it never selects ownership. This
also protects reads issued before a tab learns that another tab switched cookies.
API/auth responses disable HTTP caching and invitation referrer transmission.
Authentication query values are redacted from Uvicorn access logs.

Personal notes, progress/events, revisions, mocks, settings, plans, dashboard and
exports resolve the owner from the session. Forged owner fields are rejected and
other students' mock IDs return 404. Explicit local personal CLI commands require
an account ID. Profile paper selections constrain personal summaries, planning
and revision recommendations while shared taxonomy browsing remains complete.
New profiles use May 2027, all current papers, 20 weekly hours, 45 minutes per
subtopic, and intervals `[3, 7, 21, 60]`. The May 2027 reference is a planning target,
unverified and without an invented official exam date.

Scores use the newest successful non-shadow run matching the profile attempt.
Missing matches never substitute another attempt. Notes/progress remain available;
metadata explains unavailable scores and the plan is empty with a specific reason.
Settings updates do not recompute or change the global-current-run index.
Administrative recomputation requires an explicit existing target.

New web decisions identify their actor; legacy decisions remain unattributed.
A unit lock serializes publication and concurrent stale submissions return 409.
Revision verification counts, publication revisions, and the full scoring/reader
architecture remain later phases.

Both shells share identity handling, clear account-specific caches/drafts and note
timers on identity change, cancel reads, reject late results, handle 401 centrally,
and refresh on focus. BroadcastChannel and storage fallback notify other tabs.
Tests also reproduce unseen cookie switches and preserve unsaved own-account drafts
across settings refreshes and temporary identity-check network failures. Explicit
local demo mode stays labeled and cannot mutate authenticated data.

## Recovery and rollout evidence

The forward-only `0003_identity` widens owner IDs, preserves all old values, marks
unbound owners pending, creates identity/session/invitation tables and actor
references, and correctly replaces the old serial generator. A regression preserves
all seven personal tables and a legacy decision at owner ID 32767, then generates
32768. Study-hour precision allows small positive budgets without rounding to zero.

- [Restored migration evidence](Phase2_Restored_Migration.json)
- [Normal migration evidence](Phase2_Normal_Migration.json)
- [Normal restricted roles and routes](Phase2_Local_Verification.json)
- [Real Auth0 binding and session revocation](Phase2_Auth0_Verification.json)
- [OpenAPI and asset checksums](Phase2_Build_Verification.json), build `af852f4-a4c4aff64eb5`
- [Original checkpoint manifest](../data/backups/caf_20261002_161800_834668_7c6a7aba/manifest.json)
- [Original restore verification](../data/backups/caf_20261002_161800_834668_7c6a7aba/verification_141908d3699544b2bd8dee26d44f70f1.json)
- [Post-migration checkpoint manifest](../data/backups/caf_20261002_165935_960006_74745436/manifest.json)
- [Post-migration restore verification](../data/backups/caf_20261002_165935_960006_74745436/verification_fc5df6567fdd4df796c1488b0b1303e2.json)

Owner ID 1 is now active and bound to the configured Auth0 issuer and stable subject,
with the nominated verified email and administrator role. The targeted invitation
was consumed once. The browser displayed the original Primary Aspirant name,
May 2026 target, all six papers, budgets, revision intervals and prior study activity.
Returning sign-in without an invitation resolved the same account. Both the student
profile and curator account screen shared the real session. Logout displayed the
signed-out gate in both tabs, returned 401 on identity refresh, and the database
recorded zero active sessions and two revoked sessions. Live access logs showed
login and callback paths with query values removed. Raw invitation tokens, provider identities and local secrets
are not committed. The post-migration checkpoint predates this deliberate binding.

Backups now authenticate with a read-only dump role, including SELECT access to
identity sequences. Workers use explicit restricted connections. Named request
pools never fall back to migration administration. Ownership remains application
query enforcement; this phase introduces no row-level tenant model.

[Setup and recovery instructions](Phase2_Setup.md) describe separate production
administration credentials and mandatory revocation of restored sessions, pending
login transactions and unconsumed invitations before reopening a deployment.

## Remaining acceptance gates

Local Phase 2 acceptance passed, including two independent A/B browser sessions
against the harness provider and the separate real Auth0 owner flow. Production
deployment remains a later phase and requires its own HTTPS URLs and provider
allowlist. Existing dependency deprecation warnings remain; native Windows requires
its own runner.
