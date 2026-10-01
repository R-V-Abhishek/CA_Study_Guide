# Phase 1 verification — 2026-10-01

Phase 1 acceptance passed on `feat/phase1-ui-contracts`, starting from Phase 0
commit `b9ca7ef`. The student and curator applications, response contracts,
generated client, and tracked distributions are synchronized.

| Check | Command | Result |
| --- | --- | --- |
| Full isolated Python suite | `uv run pytest -q` | **116 passed**, 22.39 seconds |
| Focused HTTP planning and mutation contracts | `uv run pytest -q tests/test_phase1_backend.py tests/test_milestone6.py` | **19 passed** |
| OpenAPI export | `uv run scripts/export_openapi.py` | Matches `app.openapi()` exactly |
| Generated TypeScript client | `pnpm --dir web/packages/api-client generate` | Generated from checked-in OpenAPI |
| Applications, API client, browser fixture types | `pnpm --dir web type-check` | Passed |
| Production distributions | `pnpm --dir web build` | Both passed |
| Rendered browser acceptance | `pnpm --dir web test:browser` | **66 passed**, 2.2 minutes; 33 Chromium and 33 WebKit |
| Test container cleanup | `docker ps --filter label=caf.disposable=true --format '{{.Names}}'` | No remaining disposable containers |
| Final diff | `git diff --check` and scoped diff review | No whitespace errors or unrelated changes |

The browser runner builds both production applications before starting FastAPI.
It owns a temporary PostgreSQL 16 container, storage root, API process, and synthetic
fixtures. `reuseExistingServer: false` prevents reuse of a running backend.
Test-only fixture/reset endpoints belong to the harness, not the application.
Shutdown closes the database pool and stops the owned container.
The managed-server and browser-project configuration follows the
[Playwright server documentation](https://playwright.dev/docs/test-webserver) and
[project documentation](https://playwright.dev/docs/test-projects).

Rendered checks cover direct `/plan`, navigation, refresh, backend budgets and
duration, slow/empty/failed responses, zero and unavailable values, real names and
IDs, code resolution, combined filters, stable ties, URL reload/back/forward, and
retained return selections. They exercise progress rollback, failed and successful
notes/revisions/mock tests/curator decisions, query invalidation, serialized rapid
notes, stale acknowledgements, unsaved-navigation cancellation, full/null answers,
demo isolation, route-boundary recovery, and copyable diagnostics. Raw `7.5`
decayed marks never appears as `750%`; historical-unavailable explanations have
no fabricated formula.

Browser verification caught and resolved a curator selection race, a false dirty
note warning before detail loaded, early mock-form opening before paper options
loaded, and HTTP parsing of the plan's group parameter. Deterministic regressions
remain in the suite. The harness's initial SPA-shadowed fixture endpoint was also
corrected before final integration verification.

## Build and API identities

Both tested distributions embed build **`2dee416-f23a1c58b4f7`**. This combines the
base Git revision with a digest of frontend sources, the generated client, package
configuration, and lockfile, including changes awaiting the final integration
commit. Backend `/meta` exposes API `v1`, revision, target, and the selected
successful non-shadow score-run identity. The disposable API identifies itself as
`browser-harness`; normal-database verification reported target `2026-05` and run
`291`, scoring version `v1`.

[Build/route evidence](Phase1_Build_Verification.json) records exact asset paths,
SHA-256 checksums, normal API metadata, successful direct SPA/API routes, matching
detail/explanation run identity, and OpenAPI consistency. Normal verification was
read-only and used `uv run /private/tmp/caf-phase1-final-read.py`.

## Migration and preservation

The only forward migration is `0002_score_config_snapshot`: a nullable JSONB column
on `intel.score_run`. New recomputations record effective configuration; legacy
rows remain null. Nothing was backfilled or recomputed.

The migration first passed disposable fixture tests, then a restore of the actual
Phase 0 checkpoint. All 43 table digests matched before migration; 41 tables were
unchanged afterwards. All 87 legacy score-run values were preserved after removing
the new null field from the digest projection. Only `intel.score_run` and the
Alembic revision changed. See [restored migration evidence](Phase1_Restored_Migration.json).
This drill used the isolated worktree and the one-time
`uv run --no-sync /private/tmp/caf-phase1-restore-check.py` verifier.

A fresh checkpoint was then created and restored successfully:

- `uv run caf backup run`
- `uv run caf backup verify --dump-file data/backups/caf_20261001_151329_241178_fa282a73/caf_20261001_151329_241178_fa282a73.dump`
- [New checkpoint manifest](../data/backups/caf_20261001_151329_241178_fa282a73/manifest.json)
- [Restore verification](../data/backups/caf_20261001_151329_241178_fa282a73/verification_f6d42af27bbb44ff9f2f9de605d60fbf.json)

After all acceptance checks passed, the normal database was migrated in one
transaction using `uv run /private/tmp/caf-apply-phase1.py`. Assertions verified
all table digests, original score-run values, null snapshots, and the single-column
schema change before commit. [Normal migration evidence](Phase1_Normal_Migration.json)
records the resulting revision and preservation checks.

`uv run caf audit baseline --checkpoint-manifest data/backups/caf_20261001_135750_245563_ce8e08c1/manifest.json`
passed before and after migration. The
[final preservation audit](../data/audits/20261001T152156.411945Z-4f16c84b/baseline.json)
confirms personal and published content still matches the original Phase 0
checkpoint. Provenance category counts remain 191 confirmed synthetic, 34 suspected
synthetic, 10 authentic-source-identified, and 34 unresolved. Existing recovery
artifacts and the audited corpus were preserved. Backup/verification operations
added their ordinary operational events.

## Remaining limits

Native Windows verification is **pending**; macOS Chromium/WebKit results do not
establish Windows parity. Existing dependency deprecation warnings remain.
Authentication, whole-question publication, taxonomy/corpus remediation, scoring
architecture changes, and visual redesign remain later-phase work. Missing or
fragmented extracted answers remain explicitly unavailable or are displayed in
full as returned; Phase 1 does not repair their source content.
