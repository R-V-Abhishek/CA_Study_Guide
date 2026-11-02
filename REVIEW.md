# Repository Review — CA Final Study Companion

Review date: 2026-11-01 · Branch: `codex/browser-acceptance-2026-11-01` (HEAD `1a8e2e7`) · Version `0.2.1`

**Scope and method.** This was a read-only review. I read the manifests, configuration, CI, Dockerfile/Compose, the main API, auth, DB and frontend modules, and sampled the domain packages (`l0`–`l5`). I read the git history (94 commits). I did **not** run the test suite, linters, type-checkers or the app, and I did not touch the remote host. Statements about runtime behaviour come from the code and docs, not from execution. Where I am unsure, I say so.

---

## 1. Project summary and timeline

### What it is

A personal, self-hosted study platform for ICAI **CA Final** (scheme 2023) students. It has two halves:

1. **Content pipeline (curator/admin):** it discovers and downloads official ICAI PDFs (RTPs, MTPs, question papers, suggested answers). It then extracts and segments questions and answers (PyMuPDF plus optional Tesseract OCR), classifies them against a versioned syllabus/textbook taxonomy using an LLM (Gemini/OpenRouter) cascade with human review, and publishes immutable, hash-bound question snapshots.
2. **Study app (student):** a syllabus tree with historical "exam intelligence" scores (frequency E, weightage W, an importance score, a "why" explanation), a weekly plan, a spaced-revision queue, mock-test logging, notes, a question reader with source-PDF page crops, and coverage/readiness views.

The audience is the owner plus a small number of invited students. It runs on one home Ubuntu machine (`caf-home`), reached over Tailscale HTTPS, with Auth0 sign-in.

### Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Authlib (OIDC), PyMuPDF (`fitz`), structlog, Typer CLI |
| Workspace | `uv` workspace of 11 packages: `contracts`, `common`, `db`, `l0_taxonomy`, `l1_acquire`, `l2_extract`, `l3_classify`, `l4_curate`, `l5_intel`, `api`, `cli` |
| DB | PostgreSQL 16, six schemas (`ref`, `ingest`, `core`, `intel`, `app`, `ops`), six least-privilege login roles |
| Frontend | pnpm/turbo monorepo: two React 18 + Vite + Tailwind SPAs (`web/apps/student`, `web/apps/curator`), shared `@caf/api-client` (OpenAPI-generated types) and `@caf/workspace` (theme, Dialog, fonts), TanStack Query |
| Tests | pytest against throwaway Postgres containers (~390 test functions, ~9.8k LOC), Playwright browser specs (15 files), a small `node --test` UI test |
| Ops | Multi-stage Dockerfile, hardened `compose.production.yml`, systemd `caf.service`, `caf-host` CLI, release-please, GitHub Actions (checks + candidate bundle) |

Entry points: `caf_api.main:app` (uvicorn, serves the API and both SPAs), `caf` CLI (`packages/cli/caf_cli/main.py`), `caf-host` CLI (`packages/cli/caf_cli/host.py`), intelligence worker (`caf intel worker` → `caf_l5/worker.py`). There are also local launchers `setup.py`, `start.py` and `stop.py`.

### How the data model fits together (simplified)

- `ref.*`: papers, attempts, the syllabus `node` tree (paper → chapter → topic → subtopic), weightage, taxonomy versions/releases, and the anchors/instruments of the textbook taxonomy.
- `ingest.*`: acquired `document`s → extraction runs/revisions → `unit`s (question/answer parts) → `tag_suggestion`s from the LLM.
- `core.*`: human `decision`s, `appearance` + `appearance_tag` (a question mapped to nodes), classification revisions/events/verifications/disputes, and immutable `published_question`/`published_source`/`question_occurrence` snapshots.
- `intel.*`: `score_run`, `subtopic_score`, `corpus_coverage`, recompute job queue.
- `app.*`: `user_account`, `invitation`, `login_transaction`, `auth_session`, plus per-user `settings`, `progress`, `progress_event`, `note`, `revision_event`, `mock_test`, `study_session`.
- `ops.*`: alembic version and pipeline runs/audit.

### Timeline (from git history)

| Date | Milestone |
|---|---|
| 2026-09-24 | Initial commit plus Milestones 0–5 in one day: L0 registries, syllabus/tracker API, L1 crawler, L2 extraction, L3/L4 classification and atomic publish, L5 intelligence scores |
| 09-25 | M6 plan/revision/mock tests/CLI; M7 depth gate and shadow scoring; M8 backups, alarms, model eval |
| 09-26 – 09-28 | Audit fixes; live ICAI discovery; **web phases 1–3** (turborepo, student app, curator workbench = M9); cross-platform launchers; Gemini classifier and calibration benchmark |
| 10-01 | **Phase 0/1**: isolation and verified recovery baseline; about 15 fix/test commits making curator and student contracts honest |
| 10-02 – 10-07 | **Phases 2–6**: invited Auth0 accounts and private profiles; versioned textbook taxonomy; revisioned extraction; trustworthy classification and collaborative verification; question reader |
| 10-08 – 10-10 | **Phase 7**: redesigned study workspace, admin readiness workspace, about 30 UI/a11y/race-condition fix commits, curator source-PDF evidence |
| 10-14 – 10-18 | **Phase 8**: real-corpus preview, production container, baseline adoption (`baseline-2026-10-16`) |
| 10-18 – 10-27 | Production Compose, offline release bundles, GitHub Actions, host install and recovery checks → **v0.2.0** |
| 11-01 | PDF access fix in production images → **v0.2.1**; home deployment, recovery and signed-in browser acceptance recorded |

Pattern: a very fast feature-first build (M0–M9 in about 4 days, about 1.33M inserted lines including corpus artifacts), then a long "make it honest" hardening period. The later commits are almost all correctness, provenance, recovery and accessibility work.

### Current state

**Complete and production-accepted (per `docs/Deployment_verification_2026_11_01.md`, not re-verified by me):** v0.2.1 running web, worker and Postgres on `caf-home`; Auth0 sign-in; study workspace; question catalogue/reader; source PDF page rendering; recovery snapshot and encrypted Mac copy.

**Half-done / pending (as the repo itself says):**
- There is no safe upgrade path for an existing installation (`caf-host` has only `preflight`, `verify_bundle` and `inspect_backup`; `packages/cli/caf_cli/host.py:186-215`). The last activation was a one-time manual procedure.
- Scheduled encrypted backups, retention, the external backup drive, and a reboot acceptance test are all pending (AGENTS.md handoff).
- Applicability review against the May 2027 syllabus is pending. The UI states this (`web/apps/student/src/pages/QuestionReader.tsx:28`).
- Paid model calls are disabled in production (`compose.production.yml`: `GEMINI_API_KEY: ""`, `OPENROUTER_API_KEY: ""`), so classification is an offline/admin activity.

**Likely abandoned or dead:**
- Frontend dependencies that are declared but never imported (see §3.4).
- 14 phase-specific scripts in `scripts/` that nothing references (`phase2_apply`, `phase4_prepare`, `phase5_sample`, `phase6_prepare`, `intel_worker`, …).
- `recompute_legacy_scores` (`packages/l5_intel/caf_l5/scoring.py:72`, about 400 lines). It is reachable only when no non-legacy taxonomy release exists (`scoring.py:565-571`). Production has an active taxonomy, so this is probably dead in practice. I did not confirm whether any test still exercises it.
- The legacy in-app backup (`/api/v1/system/backups`, `caf_common/backup.py`) now runs in parallel with the newer `caf-host` recovery-snapshot process.
- No `TODO`/`FIXME` markers were found in `packages/`, `web/apps` or `scripts`.

---

## 2. Area-by-area review

### 2.1 Architecture and module structure

**Good**
- The layered pipeline packages (`l0`→`l5`) follow the data flow, with `contracts` (Pydantic DTOs) and `db` (models/migrations) shared underneath. Package boundaries are real `uv` workspace members, not just folders.
- A single process serves the API and both SPAs (`packages/api/caf_api/main.py:110-146`), with traversal checks (`is_relative_to`) on the SPA fallback. This keeps deployment simple for a one-host app.
- Each request class uses its own DB pool and role (`packages/db/caf_db/engine.py:12-50`): student, identity, curation, operations, pipeline, backup. Each connection checks on connect that it is not a superuser (`engine.py:42-48`). This is unusually disciplined.
- Background recompute uses a Postgres-backed job queue with `FOR UPDATE SKIP LOCKED` (`packages/l5_intel/caf_l5/jobs.py:54`) instead of adding Redis or Celery.

**Weak**
- **`routes.py` is a 1,089-line grab-bag** (`packages/api/caf_api/routes.py`). It mixes study endpoints, admin system endpoints ("Milestone 8", `:903-1024`), profile settings and export. The other routers (`questions.py`, `curate.py`, `readiness.py`) are already split by domain. This one is not.
- **Business logic sits inside route handlers.** `list_papers` (`routes.py:152-240`) and `get_dashboard` (`:586-694`) compute aggregates inline instead of calling `caf_l5`.
- **Imports inside functions are common** (`routes.py:127`, `:909`, `:930`, `:951`, `:970`; `questions.py:72`; `scoring.py:552-555`). Some prevent circular imports (`questions` ↔ `published_pages`). That is a sign the module boundaries are slightly wrong.
- **Root-level clutter:** `worker_lifecycle.py`, `setup.py/.sh/.bat`, `start.*`, `stop.*` and `BUILD_LOG.md` sit at the repo root. `docs/` holds 129 files (126 MB on disk) mixing live runbooks with frozen phase evidence JSON. `artifacts/phase5/` adds 1,010 tracked LLM-pilot files (31 MB).
- There are two `alembic.ini` files (root and `packages/db/alembic.ini`). I did not check whether they differ. If they do, it is a source of confusion.
- SPA dist paths are relative to the working directory (`main.py:110-111`, `Path("web/apps/student/dist")`). Serving silently turns off if uvicorn starts from another directory, because of the `if STUDENT_DIST.exists()` guards.

### 2.2 Backend: API design, business logic, error handling, validation

**Good**
- Request models use `extra="forbid"`, `Literal` enums, bounded numerics and `allow_inf_nan=False` (`routes.py:95-122`, `:1001-1024`). Profile settings validation is careful: unique papers, strictly increasing positive intervals (`routes.py:1012-1024`).
- Ownership checks are consistent. Every personal mutation re-checks that the node belongs to the user's resolved study context (`routes.py:523`, `:570`) and filters by `user_id`.
- Error codes are stable and machine-readable (`session_expired`, `csrf_rejected`, `identity_changed`, `published_question_not_found`), and the frontend can branch on them.
- Published content is hash-bound and immutable. Source PDFs are served only if the content-addressed path equals the approved path and the source is referenced by a current publication (`questions.py:167-190`).
- Page rasterisation has a bounded, locked LRU (`published_pages.py:24-53`, 48 MB budget). Its keys include inode, size and mtime, so a replaced file invalidates its entries.

**Weak**
- **Unbounded text inputs.** `NoteUpdateRequest.notes: str` (`routes.py:100-102`) and `MockTestCreateRequest.label`/`notes` (`:114`, `:118`) have no `max_length`. Any signed-in user can store arbitrarily large rows. The user base is small, but this also affects export size and backup size.
- **Mutations log no-op events.** `update_subtopic_progress` writes a `ProgressEvent` even when the status did not change (`routes.py:528-556`). Re-marking a subtopic `done` also overwrites `last_revised_at` (`:543-544`), which mixes "revised" with "clicked done again".
- **Exception detail leaks into responses.** `api_trigger_backup` returns `f"Backup failed: {exc}"` (`routes.py:963-964`). This is admin-only, but `pg_dump` errors can contain host and role names. `api_list_backups` returns absolute server paths (`:938`). The route also catches bare `Exception`, which goes against the repo's own "fail clearly" rule.
- **The backup runs synchronously inside a request** (`routes.py:948-964`). A large `pg_dump` can block one of the single uvicorn worker's threadpool slots and hit proxy timeouts. I did not measure dump time.
- **A route handler is called as a plain function**: `api_list_mock_tests(None, session, account)` in the export (`routes.py:1087`). This works now but breaks quietly if that handler starts using `Depends`-injected parameters.
- **Business constants are hard-coded:** the default target attempt `"2027-05"` and a default study profile in `bind_identity` (`auth.py:207-208`, and again in `caf_common/settings.py:13`); `usable_exam` source families `{'QP','question_paper','exam'}` (`routes.py:147`); the P5 paper ID and "May 2027" text in the UI (`QuestionReader.tsx:28`). These will go stale at the next attempt rollover.
- **Inconsistent code style between routers.** `questions.py` uses dense, unspaced style (`router=APIRouter(...)`, `db:Session=Depends(...)`, `:22`, `:64-80`). `routes.py` and `auth.py` use PEP 8. `ruff` is configured in `pyproject.toml` but never runs (see §2.8).
- The Hindi-language preference is not enforced on the raw PDF endpoint (`questions.py:195` lacks `require_question_language`, which the page endpoint at `published_pages.py:179` has). This is a preference, not a security boundary, so the impact is low.

### 2.3 Database: schema, relations, indexes, migrations, N+1

**Good**
- Constraints live in the database: check constraints on roles, statuses and outcomes (`models/app.py:29-31`, `:126`, `:142`); a unique `(issuer, subject)` (`:29`); partial unique indexes enforcing "one current extraction revision" (`models/extraction.py:16`), "one active taxonomy release" (`models/taxonomy.py:13`) and "one current score run" (`0001_initial_schema.py:176`).
- A GIN full-text index on published questions (`models/questions.py:49`).
- Migrations are deliberately forward-only for history-bearing data (`0003`–`0007` `downgrade()` raise with a "restore a verified checkpoint" message). This is the right call given the preservation rules.
- `grants.py` revokes and re-grants explicitly and idempotently, with no default privileges. It escapes passwords through `quote_literal` (`packages/db/caf_db/grants.py:16-60`).

**Weak**
- **Missing per-user indexes.** `app.revision_event`, `app.mock_test` and `app.study_session` have no index on `user_id`; only `progress_event(user_id, at)` and `auth_session(user_id)` are indexed (the `create_index` calls in `0001`/`0003`). The revision queue (`get_revision_due_list`) and mock-test listing filter by user. At today's scale (a few users) this does not matter. It will once the event tables grow over a full study cycle.
- **There is no row-level security on `app.*`.** `caf_app` has `SELECT, INSERT, UPDATE, DELETE` on every personal table (`grants.py:56`). Isolation between students depends entirely on every query including `user_id == account.id`. The code I read does this consistently, and the role split already limits damage. RLS keyed on a session variable would be defence in depth. This is a judgement call, not a bug.
- **Auth tables grow forever.** Nothing deletes expired `login_transaction` rows or revoked/expired `auth_session` rows. The only bulk operation is a revoke-all in `caf_cli/auth.py:40-41`. `/auth/login` is unauthenticated and inserts a row on every hit (`auth.py:167-171`).
- **N+1 in `list_papers`.** Inside `for p in papers` (`routes.py:168-240`) it runs a node query, a progress count, `_scores(...)` (which calls `resolve_context` again, `:76-82`) and a progress-status query for every paper. `get_dashboard` loops the same way (`:622`). With 6 papers that is roughly 25+ queries per page load. The `cache_study_context` session flag (`routes.py:51-54`) suggests context resolution was already a known hotspot.
- `require_account` opens its own identity session and **commits a `last_seen_at` write on every authenticated request** (`auth.py:82-100`). That is a write transaction on every GET, including every rendered PDF page image.

### 2.4 Frontend: components, state, UX, accessibility, responsiveness

**Good**
- Routes are lazy-loaded (`web/apps/student/src/App.tsx:14-24`). TanStack Query is the only state layer, with sensible defaults (`App.tsx:25`, `retry: false`, `staleTime: 120s`).
- Query keys include the account (`accountKey()`), and a server-checked `x-expected-account-id` header handles stale tabs after an account switch (`auth.py:89-93`).
- Accessibility work is visible and tested: a skip link, `aria-label`'d navigations, `role="status"`/`role="alert"` for save state, `aria-pressed` toggles (`App.tsx:58-63`, `SubtopicDetail.tsx:128`, `MockTests.tsx:33`). Many commits in 10-08 → 10-09 fix focus, dialog launchers and duplicated announcements.
- Responsive layouts are deliberate (tablet menu, mobile overlays). Playwright specs cover several viewports (per commit history; I did not run them).
- Markdown notes render with `react-markdown` without `rehype-raw`, so user HTML is not injected.
- Demo mode with fixtures (`lib/demo.ts`, `lib/fixtures.ts`) lets you inspect the UI without a backend.

**Weak**
- **Very dense JSX.** 310 lines exceed 200 characters, and the longest line in `QuestionReader.tsx` is 2,228 characters. `MockTests.tsx:33` holds a whole form on one line, and so does `SubtopicDetail.tsx:128`. Diffs, reviews and blame on these files are almost unusable. No Prettier or ESLint config exists (`lint` in `web/package.json` points at turbo tasks that I could not find defined in the apps).
- **Large page components:** `ClassificationQueue.tsx` (29 KB), `Extraction.tsx` (22 KB), `Readiness.tsx` (19 KB), `TextbookExplorer.tsx` (18 KB). Logic, data fetching and markup are mixed in one file.
- **Declared but unused dependencies.** Student: `@tiptap/react`, `@tiptap/starter-kit`, `zustand`, `framer-motion`, `canvas-confetti`, `recharts`, `zod`. Curator: `@tanstack/react-table`, `zod`, `zustand` (no import found in `apps/*/src` or `packages/*`). They add install time and supply-chain surface. Tree-shaking probably keeps them out of the bundle, but I did not inspect the bundle.
- **The workspace package is imported by relative path.** `import { Dialog } from '../../../packages/workspace/Dialog'` (`App.tsx:11-12`, `QuestionReader.tsx:10`) appears in 16 places, even though `@caf/workspace` is a declared dependency.
- **Cache invalidation by module counter.** `lib/data.ts:6-9` increments a module-level `contextGeneration` inside query keys when the profile changes, instead of `queryClient.invalidateQueries`. The old cache entries stay in memory until GC, and the pattern is easy to miss.
- **Committed build output.** `web/apps/{student,curator}/dist` (51 files, about 3 MB) are tracked "for zero-node portability" (`.gitignore`). The Docker image rebuilds them, so the tracked copies serve only the local launcher. Nothing checks that they match `src` (they are in sync today, both last touched in `a01cef8`).

### 2.5 Security

**Good** (this is the strongest area of the codebase)
- OIDC with PKCE S256, nonce, state, a browser-binding cookie, one-time login transactions, and explicit issuer/audience checks (`auth.py:153-255`). Accounts bind by issuer/subject only, never by email. Invitations require `email_verified` and an exact email match (`auth.py:177-210`).
- Sessions are opaque random tokens stored as SHA-256 hashes, with a 7-day absolute and 24-hour idle expiry. They are revocable, and disabling an account revokes its sessions (`auth.py:84`, `:367-368`).
- CSRF: a per-session token plus an Origin allow-list on non-GET requests (`auth.py:94-97`). Cookies are `HttpOnly`, `Secure` and `SameSite=Lax` (`auth.py:126`).
- Open-redirect protection decodes up to 3 times and rejects scheme, host, `//`, backslash and control characters (`auth.py:129-139`).
- Startup refuses insecure configuration outside dev/test (`auth.py:44-54`). `/api/` responses get `Cache-Control: no-store` and `Referrer-Policy: no-referrer` (`main.py:63-74`). OpenAPI requires sign-in (`main.py:98-100`).
- Production container: read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, PID and memory limits, non-root UID, backend bound to 127.0.0.1, no Docker socket (`compose.production.yml`). GitHub Actions are pinned by SHA with `persist-credentials: false` (`.github/workflows/checks.yml`).
- The test harness blocks external sockets and non-allow-listed databases (`tests/conftest.py:42-66`).

**Weak**
- **No browser security headers for the SPA.** There is no `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors` or `X-Content-Type-Options` on HTML and asset responses (`main.py:63-74`). Only the page-image endpoint sets `nosniff` (`published_pages.py:186`). Tailscale-only access limits exposure, but a CSP is cheap given that there is no inline-script requirement (I did not verify this).
- **No rate limiting** on `/auth/login`. Each hit writes a DB row. The same applies to `/api/v1/search` and the CPU-heavy PDF rasterisation endpoints.
- **Weak defaults in settings.** `DatabaseSettings.password = "postgres_dev_password"` and `PG_SUPERUSER_PASSWORD = "postgres_dev_password"` (`caf_common/settings.py:30`, `:65`). Production Compose requires real values (`:?`), and the serving roles refuse administrative fallback (`engine.py:26-34`). But the migration path falls back to `settings.database.url` (`engine.py:24`), so a misconfigured admin container would try the dev password. Failing hard in `env=production` is safer.
- **Unauthenticated health endpoint discloses information.** `/api/v1/health` returns `env` and `target_attempt` (`main.py:93-95`). This is minor. `/api/v1/ready` is already minimal.
- **Admins can lock themselves out.** `update_account` lets an administrator demote or disable themselves or the last remaining admin (`auth.py:356-370`). Recovery would then need the CLI or the DB.
- **No automated dependency audit.** CI has no `pip-audit`, `pnpm audit` or Dependabot/Renovate config (`.github/` has only three workflows). Combined with the unused frontend dependencies, this widens the attack surface that nobody watches.

### 2.6 Performance

**Good**
- The raster LRU and `Cache-Control: immutable` on fingerprinted assets (`main.py:69-71`).
- Pagination is bounded (`page_size le=100`) on the question list and search (`questions.py:131`, `:139`).
- Recompute work runs off the request path, in the worker and job queue.

**Weak**
- The per-request `last_seen_at` commit (§2.3) and the N+1 loops in `list_papers`/`get_dashboard` (§2.3).
- **Single uvicorn worker** (`Dockerfile` CMD, `compose.production.yml` `--workers 1`). Sync handlers run in the default threadpool (40 threads). PDF rasterisation (`fitz`, `published_pages.py:153-163`) and `pg_dump` are CPU/IO-heavy, so one heavy reader can slow everyone. This is acceptable for a few users. Note it before inviting more.
- `require_question_language` runs a regex over the full `search_text` on every question read (`questions.py:38-44`). This is cheap per call. A boolean `is_hindi` column filled at publish time would be cleaner and indexable.
- I took no performance measurements. All of the above comes from reading code.

### 2.7 Testing

**Good**
- About 390 pytest tests against **real PostgreSQL** in isolated containers, with template-database cloning per test (`tests/conftest.py`). Tests cover migrations (normal and restored), grants, ownership, auth, recovery, publication, readiness and release bundles (`deploy/tests`).
- The network guard in tests prevents accidental paid LLM calls (`conftest.py:56-66`, `GEMINI_API_KEY=""`).
- 15 Playwright specs cover auth, the student flows, the curator, the reader, readiness and responsive layouts.

**Weak**
- **CI does not run the Playwright suite.** `checks.yml` runs pytest, compose verification, `type-check`, `test:ui` (one file, `web/tests/ui/theme.test.cjs`) and `build`. Most of the accessibility and race-condition fixes from October are therefore protected only by local runs.
- **Test files are named by delivery phase**, not by feature (`test_milestone1.py` … `test_phase7_readiness.py`). Finding the tests for "revision queue" or "auth sessions" means grepping. New behaviour gets bolted onto whichever phase file is current.
- No test checks that `web/packages/api-client/src/generated.ts` (7,839 lines) matches `openapi.json` or the live FastAPI schema. Nothing in CI references either file. Contract drift is possible.
- No frontend unit or component tests beyond the theme test. Logic in `lib/` (`syllabus.ts`, `navigation.ts`, `url.ts`, `export.ts`) is tested only through browsers.
- I could not see coverage measurement anywhere.

### 2.8 Code quality

**Good**
- Docstrings are short and state an invariant ("Issuer/subject lookup never links an existing account by email", `auth.py:178`). Comments explain *why* (`auth.py:90-92`, `grants.py:36-37`).
- Typed Pydantic contracts sit between layers (`packages/contracts`).

**Weak**
- **Linting and type checks are configured but never enforced.** `pyproject.toml` declares `[tool.ruff]` and `[tool.mypy] strict = true`, but the only dev dependency is `pytest`, and CI runs neither tool. The visible style split between `questions.py` and `routes.py` is the result. I did not run ruff or mypy, so I do not know how many violations exist.
- Dense one-line style in both Python (`questions.py`) and TSX (§2.4).
- Duplication: `require_account` is both a router-level dependency (`routes.py:46`, `questions.py:22`) and a per-handler parameter on every endpoint. It is cached on `request.state`, so it is not executed twice, but the pattern is noisy. `get_db` (`routes.py:49`), `get_db_session` (`engine.py:59`) and `get_identity_db` (`auth.py:39`) are three near-identical session providers.
- Dead or legacy code: §1 (the unused scripts, `recompute_legacy_scores`, unused npm dependencies, the legacy backup API).
- Workspace package versions (`caf-api 0.1.0`) differ from the root `0.2.1` and API `version="1.0.0"` (`main.py:38`). Three version numbers can confuse diagnostics.

### 2.9 DevOps: environment config, build, CI/CD, logging, monitoring

**Good**
- A reproducible multi-stage Docker build with pinned uv (`0.11.19`) and pnpm (`12.6.0`), `--frozen` installs, a required `SOURCE_REVISION`, and OCI labels (`Dockerfile`).
- Release-please versioning, a release-version check in CI, and candidate bundles uploaded as artifacts (`checks.yml`, `release-bundle.yml`).
- Compose has health checks, log rotation (`10m × 3`), resource limits and named networks (`backend`, `egress`), so the DB has no egress.
- `/api/v1/ready` checks DB connectivity, the alembic head and storage permissions (`health.py:24-41`). An auth-specific access-log filter keeps tokens out of logs (`main.py:28`).

**Weak**
- **No upgrade path for an installed release** (acknowledged in AGENTS.md). Every future release currently needs a hand-run procedure. This is the largest operational risk.
- **Backups are not scheduled** and retention is not automated (acknowledged). The in-app `/system/backups` covers part of this, which is confusing next to the `caf-host` recovery snapshots.
- **Logging is inconsistent.** `caf_common/logging.py` sets up structlog with `ConsoleRenderer` (human-readable, not JSON). The worker calls `logging.basicConfig` (`caf_l5/worker.py:13`). The API mostly uses stdlib `logging`. There are no request IDs.
- **Monitoring is pull-only.** `caf_common/alarms.py` computes alarms when an admin opens `/system/health`. Nothing pushes an alert when readiness fails, the worker dies or a job fails.
- `config/models.toml` is out of date. `primary`/`fallbacks` name `gemini-3.x` models, but `[pricing]` lists only `gemini-1.5/2.0/2.5`, so budget estimates for the primary model fall back to the hard-coded `{input: 0.50, output: 3.00}` (`caf_l3/llm.py:305`). Production disables the keys, so this matters only for local classification runs.
- CI triggers on a stale branch name (`feat/phase8-central-deployment` in `checks.yml`).
- The production Postgres image is a tag (`postgres:16-bookworm`), not a digest. Release bundles may pin image IDs (per AGENTS.md), but Compose itself does not.

### 2.10 Documentation

**Good**
- `AGENTS.md` is an excellent operating contract: boundaries, commands, data-preservation rules and an honest handoff that separates "historical checkpoint" from "live status".
- `docs/Home_hosting.md` is the operational entry point. Deployment, recovery and verification records give exact identities and limitations.
- Each package has a README.

**Weak**
- **`README.md` is significantly out of date.**
  - It says "publication revisions and full published-content reading remain later implementation phases". Both shipped in Phases 5–6.
  - It describes Gemini as the classifier with `setup.py`/Docker Desktop as the main path. Production is the hardened Compose stack on Ubuntu, with paid calls disabled.
  - It advertises "debounced auto-save" notes. The notes have a manual Save button (`SubtopicDetail.tsx:128`).
  - It advertises "confetti completion" and charts. `canvas-confetti` and `recharts` are never imported.
  - It says "264 seeded subtopics", while the textbook taxonomy has since replaced the seed. I did not count the current nodes.
- **Too many documents, and the live ones are hard to find.** 129 files sit in `docs/`, mostly frozen phase evidence (`Phase*_*.json`, screenshots). There are also three overlapping plans: `Implementation_plan.md`, `CA_Final_Technical_Implementation_Plan_v2.md` and `CA_Final_Detailed_Implementation_Guide.md`. `BUILD_LOG.md` and `VERIFY.md` sit at the root. A newcomer cannot tell which plan is current.
- No architecture diagram or data-model overview. The relationships in §1 had to be rebuilt from the models.
- `output/` (untracked) holds LaTeX/PDF setup and student manuals that are not in the repo. Whether they are current is unknown.

---

## 3. Improvement list

| # | Problem | Why it matters | Suggested fix | Effort | Impact |
|---|---|---|---|---|---|
| 1 | No safe upgrade workflow for an existing installation (`caf_cli/host.py` has only preflight/verify/inspect) | Every release needs a hand-run, error-prone activation on the only production host | Implement `caf-host upgrade`: verify bundle → capture and verify a recovery snapshot → schema-compatibility check → load images → switch the Compose pointer → readiness → keep the previous release for rollback. Reuse the existing verify/inspect pieces | L | high |
| 2 | Backups not scheduled, no retention; two backup systems (`/system/backups` vs `caf-host` snapshots) | One disk failure loses private notes and progress, which the repo's own rules say must be preserved | Add a systemd timer for the snapshot and encrypted-copy flow with retention. Remove or relabel the legacy in-app backup API so there is only one recovery path | M | high |
| 3 | Playwright suite not in CI | October's a11y and race-condition fixes can regress silently | Add a CI job running `pnpm test:browser` against the Compose stack, or at least the demo-mode and fixture specs | M | high |
| 4 | ruff/mypy configured but not run | Style drift (`questions.py` vs `routes.py`); `strict=true` gives no protection | `uv add --dev ruff mypy`, run `ruff check` in CI (format later), and start mypy on `caf_api`/`caf_db` with a baseline | S–M | med |
| 5 | Unbounded `notes`, `label`, `notes` fields (`routes.py:102,114,118`) | Unbounded storage, export and backup growth from any account | Add `Field(max_length=…)` (e.g. 100k for notes, 200 for label) and a DB `CHECK (length(body) <= …)` in a forward migration | S | med |
| 6 | Auth tables never cleaned; unauthenticated `/auth/login` inserts rows; no rate limiting | Slow table growth; a trivial way to exhaust the DB | Delete expired login transactions and expired/revoked sessions periodically (worker tick or timer). Add a simple per-IP limit at the proxy or in middleware | S | med |
| 7 | No CSP, frame-ancestors or nosniff on SPA/HTML (`main.py:63-74`) | Defence in depth against XSS and clickjacking, nearly free | Extend the existing middleware with `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; img-src 'self' data: blob:` and `X-Content-Type-Options: nosniff`. Check against the Vite output first | S | med |
| 8 | N+1 loops in `list_papers` / `get_dashboard` (`routes.py:168-240`, `:622`) | About 25+ queries per dashboard load. Latency grows with papers and users | Resolve context once, then group by `paper_id` (`GROUP BY` counts, one scores call per run). Move the logic into `caf_l5` | M | med |
| 9 | `last_seen_at` commit on every authenticated request (`auth.py:99-100`) | A write transaction for every GET and page image | Update only when older than about 5 minutes (`if now - session.last_seen_at > 5min`) | S | med |
| 10 | Missing `user_id` indexes on `revision_event`, `mock_test`, `study_session` | Revision-queue and mock queries scan whole tables as history grows | Forward migration adding `(user_id, node_id, at)` on `revision_event` and `(user_id, taken_on)` on `mock_test` | S | low→med |
| 11 | Unused frontend dependencies (tiptap, zustand, framer-motion, confetti, recharts, zod, react-table) | Supply-chain surface, install time, misleading README | Remove them with pnpm. Confirm with `rg` and the build | S | low |
| 12 | Dense one-line TSX and Python; no Prettier/ESLint | Reviews and blames are impractical; harder for agents and humans to edit safely | Add Prettier (and ruff format) and reformat in a single mechanical commit recorded in `.git-blame-ignore-revs` | S (+review) | med |
| 13 | `routes.py` monolith plus in-function imports | Hard to navigate; hidden circular dependencies | Split into `study.py`, `profile.py`, `system.py` routers. Move `approved_source`/`current_question` into a shared module to break the `questions`↔`published_pages` cycle | M | low→med |
| 14 | Hard-coded attempt and paper constants (`auth.py:207`, `settings.py:13`, `routes.py:147`, `QuestionReader.tsx:28`) | Breaks or misleads at the next attempt rollover | Read defaults from `ref.attempt`/config. Send the applicability text from the backend with the baseline metadata | S–M | med |
| 15 | Admin can demote or disable the last administrator (`auth.py:356-370`) | Lockout that needs DB or CLI surgery | Reject when the change would leave zero active administrators | S | low |
| 16 | No OpenAPI ↔ `generated.ts` drift check | Silent contract drift between the API and both SPAs | Add a CI step that runs `scripts/export_openapi.py` plus codegen and `git diff --exit-code` | S | med |
| 17 | `README.md` stale; `docs/` overloaded with three overlapping plans | Misleads new users and agents about what exists | Rewrite the README around current reality (Compose deployment, Auth0, what is shipped and pending). Move phase evidence to `docs/archive/` and mark one plan as current | S–M | med |
| 18 | Phase-named test files | Hard to find coverage per feature | Over time, as tests are touched, move them into `tests/{auth,study,publication,…}`. No big-bang rename | M | low |
| 19 | Dead code: 14 unreferenced `scripts/phase*`, `recompute_legacy_scores`, legacy backup API | Maintenance cost and confusion about which path is real | Confirm that nothing in prod or tests needs them, then delete or move to `scripts/archive/`. Check `recompute_legacy_scores` test usage first | S–M | low |
| 20 | `config/models.toml` pricing lacks the configured primary/fallback models | Wrong budget estimates for local classification runs | Add pricing for every configured model, and fail at load if a configured model has no price | S | low |
| 21 | Weak dev-password defaults reachable by the migration fallback (`settings.py:30,65`, `engine.py:24`) | A misconfigured admin container silently tries a known password | Raise when `env == "production"` and no explicit `MIGRATION_DATABASE_URL` is set | S | low |
| 22 | Pull-only monitoring; logging not structured | Failures of the worker or readiness go unnoticed on an unattended home server | JSON logs from a single configuration. A timer that curls `/ready` and checks worker freshness, and sends a notification (e.g. a Tailscale-reachable ntfy) | M | med |
| 23 | Committed `dist/` with no sync check | The local launcher can serve a stale UI | Either a CI check that a fresh build equals the committed dist, or stop tracking dist and have `setup.py` build it | S | low |
| 24 | No dependency audit (pip/pnpm) | Unnoticed vulnerable dependencies | Add Dependabot or Renovate (grouped, weekly) or `pip-audit`/`pnpm audit` in CI | S | med |

---

## 4. Top 10 priorities (ordered)

1. **Build the `caf-host upgrade` workflow (#1).** Every future change depends on deploying safely without one-off procedures.
2. **Schedule encrypted backups with retention, and keep a single recovery path (#2).** The data the owner most wants to keep (private notes and progress) currently depends on someone remembering to back it up.
3. **Run Playwright in CI (#3).** It protects the largest body of recent fix work.
4. **Turn on ruff (and mypy gradually) in CI (#4)**, then do the one-time formatting pass (#12).
5. **Bound the user-supplied text fields and clean up auth tables (#5, #6).** These are small, safe changes that close the only real resource-abuse paths.
6. **Add CSP and the related headers (#7).** Almost free, and it adds a meaningful layer to an already strong auth design.
7. **Add the OpenAPI/codegen drift check (#16).** Two SPAs depend on a 7.8k-line generated file that nobody verifies.
8. **Fix the dashboard/papers N+1 and the per-request session write (#8, #9).** Do this before inviting more students.
9. **Move business constants out of code (#14).** The May 2027 attempt rollover will break them.
10. **Rewrite the README and archive the phase evidence (#17).** The current README describes a different product.

### Quick wins (each well under a day)
- Add `max_length` to `notes`/`label` (#5).
- Throttle `last_seen_at` writes (#9).
- Add the security headers to the existing middleware (#7).
- Remove the unused npm dependencies (#11).
- Add the last-administrator guard (#15).
- Fix the `models.toml` pricing gap (#20).
- Remove the stale `feat/phase8-central-deployment` trigger from `checks.yml`.
- Stop returning `str(exc)` and absolute paths from the backup endpoints (`routes.py:938`, `:964`).
- Add the `user_id` indexes migration (#10). This one needs the normal migration and recovery discipline, so schedule it with a release.

---

### Things I could not verify
- Whether the test suite, ruff, mypy, type-check and Playwright currently pass. I ran none of them.
- Actual query counts or latency. The N+1 findings come from reading code.
- Whether `recompute_legacy_scores` and the unreferenced `scripts/phase*` files are still used manually by the owner.
- Whether the two `alembic.ini` files differ, and whether the frontend `lint` turbo task is defined anywhere.
- Current production state. Everything about `caf-home` comes from repository documents dated 2026-11-01.
