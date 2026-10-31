# Repository instructions for coding agents

Read this file before editing anything in this repository. It applies throughout
the repository; also read any more specific instructions in the directory you edit.
Explicit user instructions take precedence. Keep this file useful for future agents.

## Working agreement

- Work autonomously: inspect → understand → implement → verify. Do not ask the
  owner to run commands, inspect files, or gather information you can access yourself.
- Inspect the relevant implementation, configuration, tests, and Git state before
  changing code. Prefer evidence from actual outputs over assumptions.
- Preserve working conventions and unrelated changes. Make the smallest coherent
  change; avoid speculative abstractions, dependency upgrades, and tooling changes.
- Continue through failures: inspect the cause, fix it, and rerun the relevant check.
  Do not claim success from a command's exit status alone.
- Respect an explicit stop or pause. A documentation request does not authorize
  resuming a paused deployment or changing the remote machine.
- Ask before destructive actions that can lose meaningful data or state. Inspect
  and describe the impact first. Never use `rsync --delete`, indiscriminate Docker
  cleanup, database replacement, or branch resets as shortcuts.
- Do not send messages or invitations to others without explicit authorization.
- Keep progress updates concise and report evidence, remaining limitations, and
  blockers honestly. Do not turn ordinary safe work into repeated approval requests.

## Before making an edit

1. Check `git status --short --branch` and inspect the relevant recent history.
2. Read the code and its callers, contracts, configuration, and focused tests.
3. For database work, inspect schema, constraints, ownership, and transaction boundaries.
   For APIs, inspect actual response shapes and existing authentication/error handling.
4. For tooling changes, inspect existing installations, PATH, scripts, and settings.
5. Choose the narrowest meaningful verification before implementing.

Use targeted `rg`/`rg --files` searches. Avoid broad recursive dumps, large logs,
dependency directories, generated artifacts, and source-data traversal. Use RTK
where available and useful without hiding diagnostic evidence. Never print secrets.

## Project layout and commands

- Python 3.12 workspace: `pyproject.toml`, `uv.lock`, and `packages/*`.
- API: `packages/api`; CLI and host commands: `packages/cli`.
- Database and migrations: `packages/db` and `alembic.ini`.
- Frontends: `web/`; inspect its manifests before changing scripts or dependencies.
- Developer containers: `docker-compose.yml`.
- Production image/runtime: `Dockerfile`, `compose.production.yml`, and `deploy/`.
- Verification: `tests/`, `deploy/tests/`, `scripts/`, and `.github/workflows/`.
- Operational entry point: `docs/Home_hosting.md`. Read the relevant supporting
  deployment/recovery records as well; historical checkpoints are not live status.

Use `uv` for Python, including scripts and tests. Never use `pip` for project
dependencies or plain Python to execute project code when `uv run` is available.
Use `uv add` for justified new dependencies. Do not add `from __future__` imports.
Prefer modern type hints, straightforward control flow, and Typer for CLI commands.
Understand actual structures instead of guessing with `getattr`, `hasattr`, or
`isinstance` fallback chains. Fail clearly; do not swallow exceptions.

Use the existing frontend package manager, pnpm (currently 12.6.0), and lockfile.
Do not introduce another package manager. CI's current verification commands are:

```sh
uv sync --locked
uv run --no-sync pytest -q tests deploy/tests
uv run --no-sync scripts/verify_production_compose.py
cd web
pnpm install --frozen-lockfile
pnpm type-check
pnpm test:ui
pnpm build
```

Run focused checks while iterating, then broaden when the scope warrants it.
These are not requirements to run the full application suite for a documentation
edit. Inspect current CI before relying on this list. Database tests use isolated
PostgreSQL containers; preserve existing Docker contexts, containers, and volumes.
Do not start, resize, reset, or prune Colima without first checking its state and need.

## Verification and delivery

- Test the actual failing or changed behavior, not just implementation details.
  Reuse fixtures and prefer lightweight real integration over unnecessary mocks.
- Inspect runtime output and generated artifacts when applicable. A passing
  readiness endpoint does not prove PDF reading, authentication, or recovery works.
- Review `git diff` for unintended changes, secrets, temporary logging, and churn.
- Keep documentation aligned with actual behavior. Clearly distinguish proposed,
  implemented, tested, and production-accepted functionality.
- Report what changed, why, what was verified, and any remaining uncertainty.
- Use `codex/` feature branches by default, coherent Conventional Commits, and PRs
  for integration. Inspect remote/PR state before creating duplicates. Prefer `gh`.
  Use `--body-file` for multiline PR descriptions. Do not push directly to `main`
  merely because the user asked to push a change.
- Do not delegate duplicate work. Use subagents only when authorized and when the
  task benefits from independent scopes; inspect and verify their findings.

## Data, authentication, and production boundaries

- Preserve existing account IDs, private notes/progress, shared reviews, revision
  history, unresolved quality labels, and the `baseline-2026-10-16` identity.
- Do not rerun baseline adoption or classification to repair packaging problems.
  Routine content updates must not replace production with a developer database.
- Preserve immutable source bytes/hashes and taxonomy/publication history. Do not
  weaken approved-path, ownership, authentication, or content-hash checks.
- Auth0 remains the sign-in provider. Preserve invitation restrictions and existing
  permissions. Do not enable paid model calls as a side effect of deployment.
- Keep secrets, `.env`, encryption identities, production data, and private recovery
  artifacts outside Git and release images. Never expose them in logs or tool output.
- Production data lives outside checkouts/container writable layers. Keep PostgreSQL
  private, backend access on host loopback, and external access through Tailscale HTTPS.
  Never mount the Docker socket into the web application.
- Application releases, content snapshots, and recovery snapshots are separate
  identities. A Git update alone must not activate an application release.
- Use verified immutable bundles with architecture, commit, image IDs, lock hashes,
  schema compatibility, and checksums. Do not package dirty working trees.
- Before changing an installed release, capture and verify a current recovery
  snapshot. Preserve the previous release. Never automatically downgrade a database
  or overwrite a live installation to work around missing upgrade tooling.
- Inspect current host/container/configuration state before remote changes. Do not
  infer production status solely from an old runbook or deployment receipt.

## Deployment handoff: last observed checkpoint, 2026-10-27

This is historical context, not a claim about the machine's current state. Read it
before working on deployment, then inspect live state when the user authorizes it.

- Release `v0.2.0` (commit `2821dfc0b20cad99e723b03bf8ae5e2b63747d23`)
  was installed on Ubuntu `caf-home` from a verified bundle. The restored database
  and archived files passed full integrity comparisons. The preserved database
  revision was `0009_question_language`.
- Runtime verification then found all 94 published PDF records used relative
  approved paths such as `data/blobs/...`. The image worked in `/app`, while its
  configured blob directory was `/srv/caf/data/blobs`; `/app/data` was absent.
  Published PDFs therefore failed the approved-path check despite intact files.
- Web and worker were deliberately stopped for maintenance; PostgreSQL remained
  running. Tailscale HTTPS consequently returned 502. The user explicitly paused
  deployment. Actual Auth0 study-account sign-in and PDF reading remain unverified.
- A proposed packaging fix is `/app/data -> /srv/caf/data`, with image verification
  and a real relative-path PDF regression test. It was not implemented at pause.
  Reinspect before deciding the fix; do not rewrite publication paths or bypass guards.
- `caf.service` was enabled: a reboot may restart the old image. Do not treat a
  reboot or service restart as a verified repair.
- First-install tooling exists, but a safe existing-installation `caf-host deploy`
  upgrade workflow was not yet implemented. Do not erase storage to reuse install.
- Encrypted recovery copies were verified on the Mac. The external backup drive,
  daily encrypted server backup scheduling, and retention automation remain pending.
  The recovery identity stays off Ubuntu and out of this repository.

## Owner shorthand

- `ga`: execute the agreed work; do not repeat planning.
- `pbp`: discover read-only, present a concrete plan, wait for approval, then implement.
- `ng`: do not perform the referenced action. `bb`: be brief.
- `mon`: monitor with explicit periodic status checks until completion/failure;
  never claim monitoring without checking.
- Number questions `q1`, `q2`, etc. and useful follow-ups `f1`, `f2`, etc., continuing
  the current conversation's sequence. Avoid padding with unnecessary questions.
