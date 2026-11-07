# Code review findings, 2026-11-06

Whole-repository review of `main` at `7f2a069` with the built-in `/code-review`
at **medium** effort, run in six passes: `packages/api`; `packages/db` and
`packages/cli`; the remaining `packages/*`; `deploy/`, `scripts/`, `Dockerfile`,
`compose.production.yml` and `.github/workflows`; `web/apps` and `web/packages`.

**Status: unverified.** Each finding comes from reading the code. Only two were
confirmed by evidence during review: S-02 (a test of the redaction regex) and
M-14 (the stage names actually passed to `open_run`). Reproduce each finding
before fixing it. Some will turn out to be false positives or intended behaviour.

Severity scale:

- **Critical**: a security boundary is bypassed, secrets are exposed, or user
  or recovery data can be lost.
- **High**: an outage, a wrong target, or a silent operational failure in a
  likely scenario.
- **Medium**: a crash or wrong result in edge cases; misleading operator output.
- **Low**: maintainability, performance under unusual load, dead code, duplication.

Fix in ID order. Mark each entry `Fixed in <commit/PR>`, `Not a bug: <reason>`
or `Deferred: <reason>` as it is resolved.

---

## Critical

### Security

- **S-01: Students can approve their own taxonomy descriptor edits.**
  `packages/api/caf_api/taxonomy.py:284`. The approve route needs only
  `require_account`, and `approve_descriptor` only checks that the actor is active.
  An invited student can PUT `/api/v1/taxonomy/nodes/X/descriptor` and then POST
  `/descriptor/approve`. That records a `DescriptorApproval` with no administrator
  or second reviewer, and the approved descriptor feeds classification readiness.
  Student approval itself is intended (design in `1bba797`); owner decision
  2026-11-06: the author must not approve their own revision.
  **Fixed (block):** `approve_descriptor` rejects `created_by == actor` with 422;
  `test_recursive_explorer_admin_reviews_and_private_predecessor_notes` fails
  without the fix.
  **Notification (owner choice: in-app):** `GET /api/v1/taxonomy/reviews/pending` lists the
  latest person-written, unapproved revisions by other accounts. Today shows "Waiting for
  your review" with links to `/curator/textbooks`, and "Review shared content" shows a
  count, refreshed every 5 minutes. Machine drafts (`created_by` null) are excluded. No
  email or push.
- **S-02: Backup redaction misses quoted keys and DSN credentials.**
  `packages/common/caf_common/backup.py:248`. The regex requires the key to start
  with `[\w-]`, so `"db_password": "…"` (JSON), `"api_key" = "…"` (TOML) and
  `url = "postgresql://u:pw@h/db"` are copied unredacted into `configs/` and
  every secondary copy, even though the manifest says "Credential keys redacted".
  *Confirmed by a regex test during review.*
  **Fixed:** `backup.redact_config` handles quoted keys, keeps trailing JSON commas
  and redacts URL passwords; covered by
  `test_config_redaction_covers_quoted_keys_and_url_credentials`.
- **S-03: `configure-connections` writes `.env` world-readable.**
  `packages/db/caf_db/configuration.py:37`. A new `.env` holding all six role
  passwords is created with the default umask, typically `0644`.
  **Fixed:** the file is created and kept at `0600` whenever passwords are written;
  covered by `test_configured_connections_file_is_private`.

### Recovery and host safety

- **R-01: Nightly backup retention can delete the only rollback snapshot.**
  `deploy/backup-host.sh:41`. The backup ignores `.upgrade-in-progress`, and only
  receipts from a successful finalize protect a `.previous` snapshot. Suppose an
  upgrade fails after `db migrate`. A backup the same UTC day then makes
  `plan_retention` keep only the newest snapshot that day and delete the
  pre-migration snapshot.
  **Fixed:** `backup-host.sh` refuses to run while `.upgrade-in-progress` exists,
  and `failure.json` now records `pre_migration_snapshot`, matching
  `docs/Host_installation.md`. `bash -n` and jq output checked; the Linux-only
  `scripts/verify_host_upgrade.py` asserts the new field but was not run here.
- **R-02: The install and upgrade root guards never abort.**
  `deploy/upgrade-host.sh:26`, `deploy/install-host.sh:28`. Each guard is a
  `test … && test … && test …` chain, and `set -e` does not exit when a non-final
  command in such a chain fails. So `--root /` (or a root that is not writable)
  continues, creating `postgres/`, `data/`, `releases/` and similar directories
  under `/`.
  **Fixed:** both guards now end in `|| { echo …; exit 1; }`. Reproduced the bypass
  and the fix under `bash -c 'set -e; …'`; `bash -n` passes; not run on Ubuntu.

### Student data

- **D-01: A stale note draft overwrites a newer server note.**
  `web/apps/student/src/components/SubtopicDetail.tsx:113`. The module-level
  `drafts` cache is filled from the server only when no draft exists for the key.
  Edit a note on another device, then return to the topic in the original tab.
  The refetched note is ignored, and the next keystroke autosaves the old text
  over it.
  **Fixed:** a clean draft adopts a newer server note; local edits and in-flight saves
  still win. Browser test `a newer note saved elsewhere replaces a clean draft…`
  fails without the fix.
- **D-02: A backend blip on window focus discards drafts and unmounts the app.**
  `web/packages/api-client/src/auth.ts:71`. `refreshIdentity` runs on every
  focus, and a non-401 failure (for example a 503) sets `identity: null`. That
  bumps the generation, clears the query cache and runs the reset hooks, so
  `drafts.clear()` loses unsaved notes. AuthGate then shows "Sign-in unavailable"
  even though the session is still valid.
  **Fixed:** only 401, `account_disabled` and `invite_required` clear the identity;
  other failures show "Sign-in unavailable" but keep the identity, so "Check
  again" restores the workspace and drafts (the existing network-error design).
  Browser test `a transient identity check failure…` fails without the fix.

---

## High

### API

- **H-01: Rate-limit identity likely collapses to one shared IP bucket.**
  `packages/api/caf_api/main.py:171`. The limiter falls back to
  `request.client.host`, but production runs uvicorn with `--no-proxy-headers`
  behind the Tailscale/Docker proxy. The `login` rule (20/min per IP) then acts
  as a single global bucket, so a few retries lock everyone out with 429. Check
  the real client address seen in production first.
  **Confirmed** (read-only on `caf-home`, 2026-11-06): Tailscale Serve proxies to
  `127.0.0.1:8788`, served by userland `docker-proxy`, so uvicorn sees the bridge
  gateway `172.19.0.1` for every client.
  **Fixed (pending deployment):** uvicorn uses `--proxy-headers` and trusts only the
  Docker ranges, so the limiter keys on the rightmost untrusted `X-Forwarded-For`
  entry. Covered by `test_login_rate_limit_keys_on_the_tailnet_client_behind_docker_proxy`.
  After the next release, confirm that Tailscale Serve sends `X-Forwarded-For`;
  without it, behaviour is unchanged.
- **H-02: OIDC token-exchange failures are flattened to 400 and not logged.**
  `packages/api/caf_api/auth.py:379`. `except Exception` turns Auth0 timeouts and
  5xx responses into `invalid_provider_identity`, not the
  `identity_provider_unavailable` 503 that `/auth/login` uses, and the operator
  gets no log of the cause.
  **Fixed:** httpx network and status errors return 503 `identity_provider_unavailable`;
  identity failures stay 400. Both are logged with the provider host and exception type
  only. `test_provider_outage_during_token_exchange_is_reported_and_logged` (timeout, HTML
  503) fails without the fix.

### Database and CLI

- **H-03: Migrations ignore `MIGRATION_DATABASE_URL`.**
  `packages/db/caf_db/alembic/env.py:77` (also `main.py:71`). Migrations connect
  with `DATABASE_URL` or the development default, while `db grants` uses
  `database_url('migration')`. Migrations and grants can therefore hit different
  databases, and the production guard can be bypassed.
  **Fixed:** Alembic (online and offline) and `caf db migrate` use
  `database_url("migration")`, which enforces the production rule. The CLI escapes `%`
  for Alembic's config interpolation. Production compose sets both URLs to the same value,
  so the live upgrade path is unchanged. `test_cli_migrations_target_the_migration_url`
  fails without the fix.
- **H-04: Password regeneration leaves a stale password in the stored URL.**
  `packages/db/caf_db/configuration.py:19`. When `PG_*_PASSWORD` is missing, a
  new password is generated, but the existing `*_DATABASE_URL` keeps the old one.
  The next `caf db grants` sets the new password, and every connection that uses
  the stored URL fails authentication.
  **Fixed:** a missing `PG_*_PASSWORD` is taken from the stored URL, and a URL whose
  password differs from `PG_*_PASSWORD` is refused with a clear error.
  `test_configured_connections_keep_stored_url_passwords` fails without the fix.
- **H-05: A snapshot that failed verification stays eligible for retention.**
  `packages/cli/caf_cli/host_backup.py:67`. A failed same-day snapshot is not
  removed. On the next successful run, retention keeps it as that day's newest
  snapshot and deletes the earlier verified one.
  **Fixed:** a snapshot that fails inspection or the protected-table check is renamed
  `rejected-<name>` (kept as evidence, never pruned or listed), and `status.json` records
  `rejected_snapshot`. `test_snapshot_failing_verification_is_set_aside_from_retention`
  fails without the fix.

### Deploy

- **H-06: A leftover `.new` symlink can leave boot pointing at an unverified release.**
  `deploy/upgrade-host.sh:55`. `point_to` uses `ln -s` without `-f`, and the
  rollback call ignores errors (`|| true`). The old release restarts, but
  `current-compose.json` still targets the new compose, so the next boot starts
  the unverified release.
  **Fixed:** `ln -sfn` replaces a stale `.new` link. If the rollback cannot restore the
  pointer, `failure.json` says so and `.upgrade-in-progress` is kept. Checked with
  `bash -n` and a local symlink reproduction; not run on Ubuntu.
- **H-07: Grants are applied only when the schema revision changes.**
  `deploy/upgrade-host.sh:163`. A release that adds privileges without a new
  migration activates with missing grants, and its queries fail with permission
  denied after the release is already active.
  **Fixed:** grants run on every upgrade (new `grants` phase) after any migration;
  `docs/Host_installation.md` was updated. Checked with `bash -n`; not run on Ubuntu.
- **H-08: The hourly watch blocks the nightly backup.**
  `deploy/watch-host.sh:18`. The watch holds `.deployment.lock` during
  `compose run`, and `backup-host` uses `flock -n`. If the two overlap, the
  backup exits 1 and no snapshot is taken that day.
  **Fixed:** `backup-host.sh` waits up to 10 minutes for the lock (`flock -w 600`) and
  still fails loudly if an upgrade or restore holds it longer. Checked with `bash -n`.

### Pipelines and backups

- **H-09: Hitting the budget cap marks every remaining unit failed.**
  `packages/l3_classify/caf_l3/pipeline.py:293`. `BudgetExhaustedError` falls
  into the generic `except Exception`, so the loop continues and marks each
  remaining pending unit `failed`. The run ends as `failed`, not
  `aborted_budget`.
  **Fixed (with M-15):** `BudgetExhaustedError` stops the loop like quota exhaustion,
  leaving the remaining units pending. The CLI records `aborted_budget`, which `open_run`
  now preserves. `test_budget_cap_stops_the_run_and_leaves_remaining_units_pending` fails
  without the fix.
- **H-10: A partial backup counts as the latest one.**
  `packages/common/caf_common/backup.py:311`. The dump is written before blobs
  and configs, which are read through cwd-relative paths, and nothing is cleaned
  up on failure. A dump without a manifest then satisfies `BACKUP_OK`, and a
  no-argument `verify_backup()` picks it.
  **Fixed:** any failure after the snapshot directory exists renames it
  `incomplete-<id>`, keeping the partial files but out of `list_backups`, retention and
  `BACKUP_OK`. `test_interrupted_capture_is_never_listed_as_a_backup` fails without the
  fix. Config directories are still read relative to the cwd (unchanged).

### Curator

- **H-11: Stale correction state can apply to the wrong question.**
  `web/apps/curator/src/pages/ClassificationQueue.tsx:782`. `ExtractionEvidence`
  has no `key`, and `evidenceOpen` is not reset when the item changes. The
  label/field/page state from question A is submitted against question B's
  revision. `Extraction.tsx` avoids this with `key={revisionId}`.
  **Fixed:** the panel is keyed by question and extraction revision. Browser test
  `extraction correction form resets when returning to a cached question` submits `2`
  against Q1 without the fix and `1` with it.

---

## Medium

### API

- **M-01: Duplicate weightage rows crash subtopic detail.**
  `packages/api/caf_api/study.py:508`. `scalar_one_or_none()` on a chapter that
  belongs to several weightage sections (for example different
  `valid_from_attempt` values) raises `MultipleResultsFound`, so
  `/api/v1/subtopics/{id}` returns 500. `get_paper_tree` silently keeps one
  arbitrary section.
  Latent: production has one section per chapter and no `valid_from_attempt` (read-only
  check, 2026-11-06). **Fixed:** both lookups use `_weightage_by_chapter`, which picks the
  latest section in force for the student's target attempt.
  `test_chapter_in_several_weightage_sections_uses_the_one_in_force` fails without the fix.
- **M-02: Concurrent first writes of progress or notes race.**
  `packages/api/caf_api/study.py:642`, `:688`. Check-then-insert with no upsert:
  a double-click or two tabs give an IntegrityError and a 500.
  **Fixed:** each write takes a per-student, per-topic `pg_advisory_xact_lock` before
  reading. `test_simultaneous_first_writes_do_not_collide` forces both reads before
  either insert and fails without the fix.
- **M-03: Extraction page, image and PDF routes have no rate limit.**
  `packages/api/caf_api/ratelimit.py:23`. These routes are as expensive as the
  throttled published-page routes (each hashes the whole PDF and rasterizes it),
  and students can reach them.
  **Fixed:** the extraction page, PDF and asset image routes join the `source_pages`
  per-session limit (120/min). `test_source_rendering_routes_share_the_source_pages_limit`
  fails without the fix.
- **M-04: An unexpected `group_no` crashes the dashboard.**
  `packages/api/caf_api/study.py:739`. `group_stats` has keys only for groups 1
  and 2. A paper with `group_no` 3 or 0 raises KeyError, so `/api/v1/dashboard`
  returns 500.
  Latent: production has three current papers in each of groups 1 and 2 (read-only
  check). **Fixed:** other groups get their own bucket, counted in overall progress
  only. `test_dashboard_tolerates_a_paper_outside_groups_one_and_two` fails without the fix.
- **M-05: A status correction is recorded as a revision.**
  `packages/api/caf_api/study.py:656`. done → in_progress → done sets
  `last_revised_at`, which shifts the revision schedule and dashboard counts.
  **Fixed:** status changes no longer touch `last_revised_at`, matching the
  `ProgressContract` rule that only recorded revision outcomes set it.
  `test_status_correction_is_not_recorded_as_a_revision` fails without the fix. Existing
  rows that were set this way are left as they are.

### Database and CLI

- **M-06: The validity of the migration 0010 CHECK constraint depends on the data.**
  `packages/db/caf_db/alembic/versions/0010_bounds_and_indexes.py:29`. If an
  existing row is over the limit, the constraint stays `NOT VALID`, so the
  database's schema snapshot differs from a fresh one and restore verification
  reports drift. Oversized rows also cannot be updated unless they are shortened.
  Latent: all four length checks are validated on production (read-only check).
  **Fixed:** schema comparison ignores ` NOT VALID` on CHECK constraints only, since
  it is a data property; other constraint types and changed bounds still count as
  drift (`test_check_left_not_valid_by_existing_data_is_not_schema_drift`). Oversized
  legacy rows still need shortening before they can be edited; the API already
  rejects notes over the limit, so this is deliberate.
- **M-07: A candidate cannot be upgraded to the final build of the same version.**
  `packages/cli/caf_cli/host_upgrade.py:56`. The strict `version_key`
  comparison rejects an equal version.
  **Fixed:** an equal version is accepted only when an installed candidate moves to
  the final build; final-to-candidate and same-kind repeats are still refused
  (`test_candidate_upgrades_to_the_final_build_of_its_version`).
- **M-08: A verification failure prints a spurious error.**
  `packages/cli/caf_cli/backup.py:110`. `typer.Exit` (a RuntimeError) is caught
  by `except Exception`, which adds "Verification drill failed: 1".
  **Fixed:** the `try` now covers only `verify_backup`; an unverified result exits 1
  after the report (`test_failed_verification_drill_reports_once`).
- **M-09: The watcher reports "recovered" when an alarm only changes code.**
  `packages/cli/caf_cli/host_watch.py:51`. Going from BACKUP_FAILED to
  BACKUP_STALE sends "Back to normal" alongside the new alert.
  **Fixed:** a backup code that gives way to the other backup code sends no recovery;
  only the new alert (`test_backup_alarm_changing_code_is_not_reported_as_recovered`).
- **M-10: A timezone-naive manifest `created_at` raises TypeError.**
  `packages/cli/caf_cli/host_upgrade.py:132`. The upgrade aborts with a traceback
  instead of a clear validation error.
  **Fixed:** the manifest declares `created_at: AwareDatetime`, so a naive time is
  reported as an invalid manifest (`test_snapshot_without_a_timezone_is_a_clear_validation_error`).
- **M-11: `check_role` raises TypeError when no row comes back.**
  `packages/db/caf_db/engine.py:61`. `any(cursor.fetchone())` on `None` gives an
  unclear error instead of a privilege-check message.
  **Fixed:** a missing row raises "Serving database role is not visible in pg_roles".
  Code-only: the nested connect listener has no seam, and `current_user` always has a
  row; the serving-role tests still pass.

### Pipelines, alarms and scoring

- **M-12: Failed context jobs are never retried.**
  `packages/l5_intel/caf_l5/jobs.py:235`. Any job at the current generation,
  including a failed one, counts as existing work, so freshness stays `failed`
  until the corpus generation changes.
  **Fixed:** a failed context is retried up to `MAX_FAILED_ATTEMPTS` (3) times per
  generation, no sooner than `RETRY_AFTER` (10 minutes) after the last failure; then it
  stays visibly failed (`test_failed_context_is_retried_a_bounded_number_of_times`).
- **M-13: `compute_law_stale` ignores the boundary's scope.**
  `packages/l4_curate/caf_l4/publish.py:17`. `node_ids`, `scope_node_ids` and
  the `exclude` policy are ignored, so one scoped boundary marks every earlier
  appearance in the paper stale.
  Latent: production's only `mark_stale` boundary (`ita_2025`) has no attempt yet and no
  appearance is stale (read-only check). **Fixed:** a scoped boundary applies only when
  a tagged node or one of its ancestors is in `scope_node_ids` (`test_law_staleness`).
  `exclude` remains "not stale" by design; nothing yet applies exclusion itself.
- **M-14: The extraction-failure alarm can never fire.**
  `packages/common/caf_common/alarms.py:140`. It filters on `stage == 'extract'`,
  but runs are recorded as `l2_extract` (`packages/cli/caf_cli/extract.py:101`).
  *Confirmed by the stage names passed to `open_run`.*
  **Fixed:** the alarm reads the latest `l2_extract` run. Failed documents never get
  `extract_run_id`, so the run now records `documents` and `failed` (exceptions) in its
  stats and the alarm uses those. Older runs without the count are skipped
  (`test_extraction_failure_alarm_reads_the_extract_stage`).
- **M-15: The budget alarm never fires, and would latch if it did.**
  `packages/common/caf_common/alarms.py:167`. Nothing writes
  `status='aborted_budget'`, and the query matches any historical run, not only
  the latest. Related to H-09.
  **Fixed (with H-09):** `aborted_budget` is now recorded, and the alarm fires only while
  that run is still the latest of its stage (`test_system_alarms_evaluation`).
- **M-16: The OpenRouter free-model check crashes on list pricing.**
  `packages/l3_classify/caf_l3/openrouter.py:81`. `Decimal()` on a list raises
  TypeError, and a malformed string raises InvalidOperation; neither is in the
  handled exceptions.
  **Fixed:** a model counts as free only when each listed price is a parseable zero;
  tiered (list) and malformed prices are skipped, not crashed on
  (`test_catalog_filters_paid_expired_and_missing_features`).

### Deploy and CI

- **M-17: The upgrade failure handler gives wrong recovery advice.**
  `deploy/upgrade-host.sh:62`. It always says "Services remain stopped … do not
  rerun", even when the failure happened before quiesce and the old release is
  still serving.
  **Fixed:** a failure before quiesce reports that the previous release is still serving
  and nothing changed, and clears the marker. Verified by running the extracted `finish`
  handler with stubbed Compose for pre-quiesce, rollback and post-migration failures;
  not exercised on Ubuntu.
- **M-18: `caf.service` hard-codes `-p caf`.**
  `deploy/caf.service:14`. An installation with a non-default `--project` is not
  restarted at boot, and a second project may start against the same storage.
  **Fixed:** the unit reads `.project` from `/srv/caf/installation.json` and stops if it
  cannot. Verified by running the unit's shell line with stubbed `docker`; `systemd-analyze
  verify` was not run (macOS). Production uses project `caf`, so its installed unit is
  still correct; replacing it is a manual owner step (documented).
- **M-19: A rerun of the release workflow cannot publish after a partial upload.**
  `.github/workflows/release-bundle.yml:64`. `gh release upload` has no
  `--clobber`, so the release stays a draft.
  **Fixed:** the upload uses `--clobber`; the step already refuses a release that is
  not a draft, so a published release's assets are never replaced. Verified by YAML
  parse only; it runs on the next tagged release.

### Web

- **M-20: Deep links to a question part fail in the original-pages view.**
  `web/apps/student/src/pages/QuestionReader.tsx:96`. Original pages is the
  default view, and it renders no `part-<id>` elements, so `?part=` and the
  outline anchors point at nothing.
  **Fixed:** a `?part=` link opens Extracted text, and outline links select their part
  through `?part=` and switch to that view before scrolling
  (`part links open the extracted text at that part`, fails without the fix).
- **M-21: An extraction document deep link beyond page 1 resolves to nothing.**
  `web/apps/curator/src/pages/Extraction.tsx:246`. Metadata and "Promote
  candidate revision" disappear, and the header shows "Current revision None".
  **Fixed:** new `GET /api/v1/extraction/documents/{id}`; the page uses it when the linked
  document is not on the loaded list page (browser test `a document deep link works when
  the document is not on the first list page`, fails without the fix; API test
  `test_single_extraction_document_matches_the_list_entry`).
- **M-22: The curator's Alt shortcuts never fire on macOS.**
  `web/apps/curator/src/pages/ClassificationQueue.tsx:231`. The handler compares
  `event.key`, which Option changes to characters such as ∆ and ˚. Use
  `event.code`.
  **Fixed:** shortcuts read `event.code` (physical key); the separator test now sends
  macOS Option+Q (`key: "œ"`) and fails without the fix.
- **M-23: The default mock date is the UTC date.**
  `web/apps/student/src/pages/MockTests.tsx:22`. Before 05:30 IST the date field
  is prefilled with yesterday's date.
  **Fixed:** the default uses the browser's local date. Browser test `the mock result date
  defaults to the local date` (Asia/Kolkata, 01:30 IST) received 2026-11-05 without the fix.
- **M-24: Each keystroke in a URL-bound input adds a history entry.**
  `web/apps/student/src/lib/url.ts:13`. `setSearchParams` is called without
  `{ replace: true }`, so Back steps through partial search terms.
  **Fixed:** `set` takes `{ replace }`; question search and syllabus topic search use it,
  while filters and selections still add history (`typing a search does not add a history
  entry per keystroke`, fails without the fix).
- **M-25: Caller-supplied headers drop the default Content-Type.**
  `web/packages/api-client/src/client.ts:65`. `...config` is spread after the
  merged `headers`, so passing any `headers` removes the default Content-Type
  from JSON requests.
  **Fixed:** the merged headers now come after `...config`, and `fetch` still defaults to
  `authenticatedFetch`. Code-only: no caller passes headers today; type-check and the
  student/auth browser suites (34 passed) cover the unchanged default path.

---

## Low

### API

- **L-01: Rate-limit pruning can run on every request.**
  `packages/api/caf_api/ratelimit.py:46`. Past 10,000 buckets, each allowed
  request rebuilds the dict, and it removes nothing while the keys are recent.
  Random session cookies can trigger this.
  **Fixed:** overflow prunes to half capacity, dropping idle buckets and then the least
  recently used, so memory stays bounded and pruning is amortized
  (`test_rate_limiter_memory_is_bounded_and_pruning_is_amortized`).
- **L-02: The source path guard is duplicated.**
  `packages/api/caf_api/published_pages.py:106` re-implements the sha256 and
  approved-path checks from `published.py:75-81`. Extract a shared
  `approved_blob_path` so both callers enforce the same rule.
  **Fixed:** both use `published.approved_source_path`, with identical checks; the
  existing path/hash guard tests in `tests/test_published_pages.py` pass.

### Pipelines and common

- **L-03: Each recompute does a linear node scan inside a triple loop.**
  `packages/l5_intel/caf_l5/scoring.py:860`. Build an id → node dict once.
  **Fixed:** `leaves_by_id` is built once; scoring suites pass. Not benchmarked.
- **L-04: Dead resume branch and a no-op try/except.**
  `packages/l3_classify/caf_l3/pipeline.py:91` (both branches apply the same
  filter) and `caf_l3/cascade.py:117-120`.
  **Fixed:** one unconditional status filter (the real resume filter is the later
  suggestion/open-gap block), and the re-raising `try` is gone; behaviour is unchanged.
- **L-05: Minor issues noted but not ranked:**
  - `audit.collect_baseline` defaults to `Path.cwd()`, evaluated once at import.
  - `run_context.get_git_sha` swallows every exception and returns `None`.
  - The fetcher follows redirects to other hosts without applying politeness or
    robots rules for them.
  - `llm.py` logs `status="ok"` before validating the output.
  **Fixed:** `collect_baseline` resolves the working directory per call; `get_git_sha`
  catches only `OSError`/`SubprocessError`; the LLM call is logged as `schema_error`
  until its output validates. The fetcher now follows redirects hop by hop and paces
  each new host (`test_redirects_to_another_host_are_paced_per_host`). Robots rules are
  deliberately not rechecked on redirects, matching the documented policy that robots
  governs discovery, not the download of a discovered artifact.

### Deploy

- **L-06: The sandbox flags and readiness probes are copied by hand.**
  The hardened `docker run` flag set (about 10 copies) and the
  readiness/`alembic_version` probes (about 4) appear across `caf-host`,
  `install-host`, `upgrade-host`, `backup-host` and `status-host`. Use a shared
  `deploy/lib.sh`.
  **Deferred:** a pure refactor of five production host scripts that cannot be exercised
  on Ubuntu from this checkout; the risk outweighs the duplication for now.

### Web

- **L-07: The export object URL is revoked synchronously.**
  `web/apps/student/src/lib/export.ts:9`. This can break downloads in Firefox
  and Safari.
  **Fixed:** the URL is revoked one second after the click. Browser test `profile export
  downloads the private JSON file` passes in Chromium; WebKit was not run (installed build
  2359, Playwright needs 2370) and Firefox is not configured.
- **L-08: The auth components are duplicated across apps.**
  `web/apps/curator/src/components/AuthGate.tsx` and `SessionControls.tsx` copy
  the student app's versions. Move them into `@caf/workspace`, which also means
  the D-02 fix is made once.
  **Fixed:** both apps import `@caf/workspace/AuthGate` and `@caf/workspace/SessionControls`
  (the copies were byte-identical); auth and curator browser suites pass (25).
- **L-09: `@caf/workspace` lists `react` as a dependency, not a peer dependency.**
  `web/packages/workspace/package.json:7`. If the ranges drift, two React copies
  can be installed and hooks throw "Invalid hook call".
  **Fixed:** `react` and `@tanstack/react-query` are peer (and dev) dependencies of
  `@caf/workspace`; the lockfile gained only the workspace's own entries.
- **L-10: The `@vitejs/plugin-react` floor predates React 19.**
  `web/apps/curator/package.json:20` (`^4.3.4`). The lockfile resolves 4.7.0, so
  raise the floor.
  **Fixed:** both apps declare `^4.7.0`; the lockfile changed only its specifiers and
  `pnpm install --frozen-lockfile` passes.
- **L-11: The syllabus tree focus state can go stale, which is why the router is pinned.**
  `web/apps/student/src/components/SyllabusTree.tsx:87`, with the
  `react-router-dom` v6 pin in `web/apps/student/package.json:20`. Keep focus and
  selection in local state, then the pin can be lifted.
  **Partly fixed:** focus is already local state, and `^6.28.0` has been the range since
  the Phase 1 foundation commit, so no evidence links the v6 range to the tree. The real
  defect was that ArrowRight/ArrowLeft ignored branches shown open by a filter; the keys
  now follow the displayed state (`syllabus leaf filters retain ancestors and keyboard
  navigation operates the real tree`, fails without the fix). A react-router v7 upgrade
  is a separate, unrequested dependency change and was not made.
- **L-12: The openapi-fetch 0.13 → 0.17 upgrade is unchecked.**
  `web/packages/api-client/package.json:13`. The middleware error contract
  (`errorMiddleware.onResponse` throwing `ApiError`) has not been re-verified.
  Local `node_modules` now match the lockfile, so `type-check` and the browser
  tests can cover this.
  **Verified, no change:** with openapi-fetch 0.17.0 resolved for `@caf/api-client`,
  `curator controlled responses › other curator pages report failed loads with usable
  navigation` shows the server `detail` from `errorMiddleware` on the typed-client
  Catalogue page; the curator suite passes (10) and type-check is clean.
- **L-13: Formatter churn in `Profile.tsx`.**
  `web/apps/student/src/pages/Profile.tsx:54`. Prettier flattened the nesting of
  the `dirty` and `valid` chains in a dependency commit. Cosmetic only.
  **No change:** the layout is Prettier's output, which `pnpm format:check` enforces.

---

## Summary

| Severity | Count | IDs |
| --- | --- | --- |
| Critical | 7 | S-01–S-03, R-01–R-02, D-01–D-02 |
| High | 11 | H-01–H-11 |
| Medium | 25 | M-01–M-25 |
| Low | 13 | L-01–L-13 |

The frontend design critique and redesign proposal are tracked separately from
these correctness findings.
