# CA Final Study Companion

A private, invitation-only study workspace for CA Final students, built around historical exam
questions. Students study a syllabus tree, read past questions with their source PDF pages, and see
frequency- and marks-based importance scores. Curators (any invited account) review how extracted
questions map to syllabus topics before anything is published.

This repository is one Python workspace (API, pipeline, CLI) plus two React single-page apps.
For how the pieces fit together, read [docs/Architecture.md](docs/Architecture.md). For the state of
the production deployment, read [docs/Home_hosting.md](docs/Home_hosting.md).

## What exists today

| Area | State |
|---|---|
| Student app (`/`) | Dashboard, papers and syllabus tree, per-topic progress and private notes, study plan, spaced-revision queue, mock-test tracker, published question reader with source pages, search, profile (including Hindi opt-in). |
| Curator app (`/curator`) | Catalogue, extraction review, classification queue (single and bulk review, disputes), taxonomy and descriptor review, readiness, accounts and invitations (administrators), system health. |
| Sign-in | Auth0 (OpenID Connect) with invitations. No self-registration. Sessions are opaque server-side cookies with CSRF protection. |
| Data | PostgreSQL 16 with six schemas and six least-privilege roles. Forward-only Alembic migrations. |
| Classification | Mapping suggestions are reviewed by a human before publication; model scores never authorize publication. |
| Production | Docker Compose on a private Ubuntu host, served over Tailscale HTTPS. See [docs/Home_hosting.md](docs/Home_hosting.md). |
| Ops | Offline release bundles, `caf-host install/upgrade/backup/watch/status`, scheduled recovery snapshots, health alerts. The shell orchestration for upgrade, backup and watch has not yet run on a live host. |

Features that existed in early design documents but are **not** implemented: confetti or gamified
completion, auto-saving rich-text notes, charts of mock-test scores, CSV export. Notes are plain text,
saved explicitly. The syllabus is whatever the active taxonomy release contains, not a fixed 264 nodes.

## Roles

- **Student**: reads published content; keeps private progress, notes, mock tests and settings.
- **Curator**: every invited account can review and verify classifications.
- **Administrator**: additionally manages invitations and accounts, bulk-accepts reviews and runs
  operational actions. The last active administrator cannot be removed.

## Run it locally

Requirements: Python 3.12+, Docker, [`uv`](https://docs.astral.sh/uv/), and pnpm for the frontends.

```bash
python3 setup.py     # creates .env, starts PostgreSQL on 5433, installs dependencies, migrates, loads the taxonomy
python3 start.py     # serves the API and both apps on http://127.0.0.1:8788
python3 stop.py
```

`setup.py` asks for an optional `GEMINI_API_KEY`; it is only needed for automated classification.
Local sign-in needs a development Auth0 tenant: see [docs/Phase2_Setup.md](docs/Phase2_Setup.md).

Frontend development:

```bash
cd web
pnpm install --frozen-lockfile
pnpm type-check && pnpm test:ui && pnpm build
pnpm exec playwright test --project=chromium
```

`web/apps/*/dist` is committed because the container image copies it; `pnpm check:dist` fails if it is
stale. Rebuild it with `pnpm build` after changing frontend sources.

## Tests and checks

```bash
uv sync --locked
uv run --no-sync pytest -q tests deploy/tests      # needs Docker: tests clone a disposable PostgreSQL 16
uv run --no-sync ruff check packages tests deploy scripts *.py
uv run --no-sync mypy packages/api/caf_api packages/db/caf_db
uv run --no-sync scripts/verify_production_compose.py
```

CI (`.github/workflows/checks.yml`) runs these plus an OpenAPI drift check, the dist check and the
chromium Playwright suite. No live model or acquisition calls happen in tests.

## Content pipeline (curators)

```text
acquire (ICAI PDFs) -> extract (questions/answers) -> classify (suggest syllabus topics)
   -> curate (human review) -> publish -> intel (frequency and importance scores)
```

Each stage is a `caf` subcommand (`uv run caf --help`). The step-by-step workflow, quotas and
cost controls are in [docs/PIPELINE.md](docs/PIPELINE.md). Classification never reruns on the adopted
baseline (`baseline-2026-10-16`); see [docs/Baseline_2026_10_16.md](docs/Baseline_2026_10_16.md).

## Deploying

Production runs from verified, checksummed release bundles, not from a Git checkout.

- [docs/Home_hosting.md](docs/Home_hosting.md): current deployment state (start here).
- [docs/Host_installation.md](docs/Host_installation.md): install, upgrade, snapshots, health watch.
- [docs/Application_releases.md](docs/Application_releases.md): building and verifying bundles.
- [docs/Recovery_encryption.md](docs/Recovery_encryption.md): encrypted recovery copies.

## Repository map

| Path | Contents |
|---|---|
| `packages/` | Python packages by layer: `contracts`, `common`, `db`, `l0_taxonomy` ... `l5_intel`, `api`, `cli` |
| `web/` | pnpm workspace: `apps/student`, `apps/curator`, shared `packages/*`, Playwright tests |
| `deploy/` | Host scripts, systemd units, release compatibility, deployment tests |
| `scripts/` | Verification tools and historical phase scripts |
| `config/`, `taxonomy/`, `prompts/`, `profiles/` | Scoring, source and model configuration; taxonomy data; classifier prompts |
| `docs/` | Runbooks, plans and verification evidence ([docs/archive](docs/archive/README.md) holds older reports) |
| `REVIEW.md`, `PLAN.md` | Repository review and the phased improvement plan |
| `AGENTS.md` | Rules for coding agents, including data-safety boundaries |

## Troubleshooting

- **Database refuses connections on 5433**: start Docker, then rerun `python3 setup.py`; it is idempotent.
- **Port 8788 busy**: stop the other process or run `python3 stop.py`.
- **Tests fail at startup**: they need a running Docker engine; setup failures are reported, not skipped.
- **Classification quota errors**: classification stops cleanly on quota exhaustion and can be resumed.
