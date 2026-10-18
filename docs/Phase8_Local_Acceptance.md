# Local study and review

The acceptance setup was retired on 16 October 2026. Local experience sign-off is no longer a prerequisite for engineering. The synthetic landing page, checklist, account switching and banners have been removed.

Use the standard application at **http://127.0.0.1:8788**, with ordinary Auth0 authentication and the persistent local database:

```sh
uv run start.py
```

Study is at `/`, review at `/curator/classifications`, and API documentation at `/docs`. The application target is May 2027. The adopted corpus release is `baseline-2026-10-16`; baseline adoption preserves unresolved classifications and missing answers rather than manufacturing student verifications.

The database and personal records persist across application restarts. Do not use a disposable preview or test reset against this database. The unrelated service on port 8000 is preserved.

Synthetic reader and account fixtures remain confined to the owned automated browser sandbox:

```sh
pnpm --dir web exec playwright test baseline-study.spec.ts questions.spec.ts
```

The Auth0 application must allow `http://127.0.0.1:8788/auth/callback` and the matching local origin/logout return URL. Local environment configuration uses those URLs; real provider authentication still needs to be verified against the provider's allowlist.

Earlier local acceptance and preview results remain historical evidence in [Phase 8 verification](Phase8_Verification.md) and [real-data preview history](Phase8_Real_Data_Preview.md). They do not establish cloud deployment, recovery, spending controls or production authentication readiness.
