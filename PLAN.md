# Implementation plan — review fixes (Part A) and agent-ready question association (Part B)

## Context

`REVIEW.md` (2026-11-01) found a well-secured, data-careful app with gaps in operations (no upgrade path, unscheduled backups), CI enforcement (no Playwright, ruff or mypy), input bounds, query efficiency, code readability and docs. The owner also wants question-to-syllabus association to become an **async, batch API behind a swappable engine interface**, so a future agentic classifier can replace today's logic without changing the contract, and can be measured against it.

On approval, the first execution step copies this plan to `PLAN.md` at the repo root (its own `docs:` commit on a `codex/` branch).

Decisions confirmed with the owner:
- **"Auto-accepted" = pre-approved, a human confirms.** Nothing publishes without a human action. The invariant "model scores never authorize publication" (`caf_l3/evaluate.py:142`, `caf_l4/revisions.py:348-394`) stays.
- **Inline questions and inline syllabus trees are evaluation-only.** Only referenced items (existing extraction revisions plus taxonomy releases) can reach the review queue.

## Ground rules for every phase

- One `codex/<topic>` branch and one PR per step (or per tightly coupled group), using Conventional Commits. Tests go in the same PR as the change.
- Every phase leaves `main` releasable. CI must pass: `uv run --no-sync pytest -q tests deploy/tests`, compose verification, `pnpm type-check`, `test:ui`, `build`, plus the new jobs added in Phase 0.
- **Migrations are forward-only** and additive (`0010…`). A downgrade raises, as in `0003`–`0007`. No backfill rewrites published, classification or personal history.
- **Data that must be preserved** throughout: account IDs, notes/progress/events, shared reviews, classification and publication history, unresolved quality labels, the `baseline-2026-10-16` identity, source bytes/hashes, and taxonomy history. Every migration PR includes a "restored-snapshot migration" test (existing pattern: `tests/test_migration_baseline.py`, `docs/Phase*_Restored_Migration.json`).
- **Nothing touches `caf-home` without explicit owner authorization** per release. Paid model calls stay disabled in production (`compose.production.yml` keeps `GEMINI_API_KEY: ""`) unless the owner explicitly enables an engine.
- `∥` = can run in parallel with the other `∥` steps in the same phase (different files, no shared migration).

---

# Part A — Fix plan for the review findings

## Phase 0 — CI guardrails (no runtime behaviour change; nothing to deploy)

Lands first because every later step relies on these checks to catch regressions.

| Step | Goal | Files | Approach | Risks | Verify | Effort |
|---|---|---|---|---|---|---|
| 0.1 ∥ | Lint in CI | `pyproject.toml`, `.github/workflows/checks.yml` | `uv add --dev ruff`. Start with `ruff check` using the default rule set plus `--extend-select I`, with a committed per-file `ignore` baseline. **No formatting yet** (that is 4.1). Add a CI step | Large initial violation count | CI is green; deliberately introducing a violation fails CI | S |
| 0.2 ∥ | Type-check the API and DB packages | `pyproject.toml`, CI | `uv add --dev mypy`. Run `mypy packages/api packages/db` only. Narrow `strict` to those packages; record `# type: ignore[...]` baselines rather than code churn | Strict-mode noise | CI step passes; a deliberate type error fails | M |
| 0.3 ∥ | Playwright in CI | `checks.yml` (new job), `web/playwright.config.ts` | Job: `pnpm exec playwright install --with-deps chromium`, run the demo/fixture specs first (no Auth0). Find out which specs need a live stack and gate those behind a compose service job using `scripts/browser_server.py` / `browser_oidc.py`, if they work headless (**unsure**: needs a dry run) | Flaky timing specs | Three consecutive green CI runs; upload the trace on failure | M |
| 0.4 ∥ | API contract drift check | `scripts/export_openapi.py`, `web/packages/api-client`, CI | CI runs export plus codegen, then `git diff --exit-code openapi.json web/packages/api-client/src/generated.ts`. Read the current generator command from `web/packages/api-client/package.json` first | Codegen not deterministic | A deliberate schema change without regeneration fails CI | S |
| 0.5 ∥ | Committed `dist/` stays in sync | CI | After `pnpm build`, run `git diff --exit-code web/apps/*/dist`. If builds aren't reproducible (hashes vary), choose to stop tracking dist and have `setup.py` build it instead (decide during the step and document the choice) | Non-deterministic Vite output | CI fails if dist is stale | S |
| 0.6 ∥ | Dependency audit | `.github/dependabot.yml` | Weekly grouped updates for `uv`, `npm`/pnpm and actions; security alerts only, minor updates grouped | PR noise | The Dependabot config validates | S |
| 0.7 ∥ | Small CI hygiene | `checks.yml`, `config/models.toml`, `caf_l3/llm.py:305` | Remove the stale `feat/phase8-central-deployment` trigger. Add pricing entries for `gemini-3.5…3.8-flash`. Fail at load if a configured model has no price, instead of the silent `0.50/3.00` fallback | Wrong price values | Unit test: missing price → `ValueError`; the existing `tests/test_llm_budget.py` still passes | S |
| 0.8 ∥ | Remove unused frontend dependencies | `web/apps/student/package.json`, `web/apps/curator/package.json`, `pnpm-lock.yaml` | `pnpm remove` tiptap ×2, zustand, framer-motion, canvas-confetti, recharts, zod, `@tanstack/react-table`, `@types/canvas-confetti`. Re-run `rg` before removing each one | A hidden dynamic import | `pnpm type-check && pnpm build`; Playwright from 0.3 | S |

## Phase 1 — Operational blockers (the release path)

Every later phase that ships a migration needs a safe way to install it. Code for Phases 2–5 can be **developed in parallel**, but nothing is **installed** on `caf-home` until 1.1 and 1.2 are accepted.

| Step | Goal | Files | Approach | Risks | Verify | Effort |
|---|---|---|---|---|---|---|
| 1.1 | `caf-host upgrade` for existing installations | `packages/cli/caf_cli/host.py`, `host_bundle.py`, `deploy/caf-host`, `deploy/tests/`, `docs/Host_installation.md` | Ordered, resumable steps, each with a receipt: (1) `verify_bundle`; (2) capture a recovery snapshot and verify it with the existing `inspect_backup`; (3) schema compatibility check (bundle head vs DB `ops.alembic_version`; refuse a downgrade); (4) load the images and record their IDs; (5) stop web/worker, run `alembic upgrade` with the `admin` profile; (6) switch the Compose pointer that `caf.service` follows; (7) start the services and wait for `/api/v1/ready`; (8) write the receipt. On failure before step 5, restore the old pointer. After step 5, stop and print the restore-from-snapshot procedure, with **no automatic DB downgrade** | Partial upgrade; data loss | `deploy/tests`: simulated install → upgrade on an isolated Postgres plus compose (`scripts/verify_production_stack.py` pattern): table digests preserved, previous release kept, readiness passes. Then a dress rehearsal on a staging copy before `caf-home` (owner authorization) | L |
| 1.2 | Scheduled encrypted backups with retention | `deploy/` (new `caf-backup.service` + `.timer`), `caf_common/backup.py` or the host snapshot path, `docs/Recovery_encryption.md` | Daily timer running the existing snapshot plus encryption flow (the identity stays off-host; the timer encrypts to a public recipient only). Retention: 7 daily, 4 weekly, 6 monthly, implemented as an explicit list-and-delete of snapshot dirs **older than policy, never `rsync --delete`**. Write a status file for 3.2 | Deleting the wrong snapshot | Test retention selection on synthetic dirs. Restore drill: decrypt → isolated restore → schema and table digest check | M |
| 1.3 | Single recovery path | `routes.py:927-964`, `caf_common/backup.py`, curator `System.tsx` | Make `/system/backups` **read-only status** of the 1.2 snapshots (name, age, size, verification result; no absolute paths, no `str(exc)`). Remove the synchronous `POST` | The owner may use the in-app button | Updated API tests in `tests/test_milestone8.py`; the curator System page renders the status | S |

## Phase 2 — Security, validation and DB efficiency (one migration: `0010_bounds_and_indexes`)

| Step | Goal | Files | Approach | Risks | Verify | Effort |
|---|---|---|---|---|---|---|
| 2.1 ∥ | Bounded user text | `routes.py:100-118`, `0010` | Pydantic `max_length`: notes 100 000, mock label 200, mock notes 10 000. DB `CHECK (char_length(body) <= 100000) NOT VALID`, followed by `VALIDATE CONSTRAINT` **only after** a read-only count of existing oversized rows (if any exist, keep NOT VALID and report; never truncate personal data) | Existing longer notes | API tests for 422 on oversized input; the migration test on a restored snapshot shows zero altered rows | S |
| 2.2 ∥ | Security headers | `caf_api/main.py:63-74` | Add `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` (adjust `style-src` after inspecting the Vite output), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` | CSP breaks the SPA or fonts | Test asserting the headers; Playwright suite (0.3) with no CSP console violations | S |
| 2.3 ∥ | Admin lockout guard | `caf_api/auth.py:356-370` | Under the existing `FOR UPDATE`, count other active administrators; return 409 `last_administrator` if the change would leave zero | — | Test in `tests/test_phase2_auth.py` | S |
| 2.4 ∥ | Fail hard on dev defaults in production | `caf_common/settings.py:30,65`, `caf_db/engine.py:24` | In `env=production`, `database_url("migration")` requires an explicit `MIGRATION_DATABASE_URL`. Remove the silent fallback | Breaks an undocumented admin flow | Unit test; `scripts/verify_production_compose.py` confirms the admin profile sets it | S |
| 2.5 ∥ | Health endpoint minimal | `main.py:93-95` | Return `{"status":"ok"}` only. Move env and attempt into the authenticated `/system/health` | Clients reading `env` | `rg` the frontends for `/health` usage first; update `Diagnostics.tsx` if needed | S |
| 2.6 | Per-user indexes | `0010` | `revision_event(user_id, node_id, at)`, `mock_test(user_id, taken_on)`, `study_session(user_id)`. Use `CREATE INDEX CONCURRENTLY` in an autocommit block (the tables are small; plain create is acceptable if alembic transactional DDL makes concurrent awkward) | Lock time (negligible at this size) | `EXPLAIN` in a test asserts an index scan on a seeded table | S |
| 2.7 | Session write throttle | `auth.py:98-100` | Update `last_seen_at` only when it is older than 5 minutes. Keep the 24 h idle rule exact by comparing against the stored value | Idle window drifts by up to 5 min (acceptable; document it) | Tests: two GETs → one write; idle expiry still enforced | S |
| 2.8 | Auth table cleanup | `caf_l5/worker.py` loop or a new `caf auth prune` command plus a timer | Delete `login_transaction` where `expires_at < now() - 1 day`, and `auth_session` where `revoked_at` or `expires_at` is more than 30 days old. Runs as the `identity` role (it already has DELETE) | Deleting live sessions | Tests with fixed clocks | S |
| 2.9 | Rate limiting | `main.py` middleware (in-process token bucket keyed by client IP and principal) | `/auth/login`: 20/min/IP. Page raster and PDF endpoints: 120/min/principal. `/search`: 60/min. Single worker, so in-process state is correct; note it must change if workers > 1 | Behind Tailscale serve, every client IP may look like loopback (**unsure**: check headers; the app runs `--no-proxy-headers`), so key on the principal where possible | Tests that the limit returns 429 with `Retry-After` | M |
| 2.10 | Remove N+1 in papers/dashboard | `routes.py:152-240`, `:586-694`, move into `caf_l5/service.py` | Resolve context once. One grouped query for leaf counts per paper, one for done counts, one for scores per run (`get_subtopic_scores_for_paper` gets a multi-paper variant). Preserve the response shapes exactly | Subtle number changes | **Golden test**: capture the current JSON for a seeded fixture before refactoring and assert equality after. Add a query-count assertion via a SQLAlchemy `before_cursor_execute` counter (≤ 8) | M |
| 2.11 | Remove N+1 in the classification queue | `caf_api/curate.py:217-287` | Push the `paper`, `source`, `experimental` and `disputed` filters and pagination into SQL. Batch-load publications, verifications and disputes for the page with `IN` queries. Keep `readiness()` per row, but only for the page window. Filters that need readiness (`ready=`) still work in Python, scanning in bounded chunks | Changed ordering or pagination semantics | Golden test against the current output on the fixture corpus; existing `tests/test_phase5_api.py` | M |
| 2.12 ∥ | Progress event correctness | `routes.py:514-558` | A no-op (same status) returns 200 and writes no event. A `done → done` call no longer touches `last_revised_at` (revision timing belongs to `revision_event`) | The UI may rely on the old `last_revised_at` behaviour | `rg` for `last_revised_at` in `caf_l5`; tests | S |
| 2.13 ∥ | Hindi preference on the raw PDF | `caf_api/questions.py:195` | Apply `require_question_language` to the referencing question. If a source is referenced by both Hindi and English questions, allow it when any visible question references it | — | Test | S |

## Phase 3 — Observability

| Step | Goal | Files | Approach | Verify | Effort |
|---|---|---|---|---|---|
| 3.1 ∥ | One structured logging setup | `caf_common/logging.py`, `caf_l5/worker.py:13`, `main.py` lifespan | `configure_logging(json=env=="production")` with structlog `JSONRenderer` in production, used by the API, worker and CLI. Request-ID middleware (generate or accept `X-Request-ID`, bind to contextvars). Keep `AUTH_ACCESS_FILTER` | Test that a log line is JSON and contains `request_id`, and that the auth filter still redacts | S |
| 3.2 ∥ | Push alerts | `deploy/` (`caf-watch.timer`), small script | Every 5 min: `/ready`, worker heartbeat (new `ops.worker_heartbeat` row updated each loop; read it as the backup role), last backup status from 1.2. Notify through a configured webhook (ntfy or email; the owner picks the target, and nothing is sent without configuration) | Simulated failures trigger exactly one notification (with de-duplication) | M |

## Phase 4 — Code health (behaviour-preserving)

| Step | Goal | Files | Approach | Risks | Verify | Effort |
|---|---|---|---|---|---|---|
| 4.1 | One formatting commit | all `.py`, `web/**/*.ts(x)` | `ruff format` plus Prettier (`printWidth 120`) in **one mechanical commit**, listed in `.git-blame-ignore-revs`. Then enforce both in CI. Schedule it when no other branches are open, to avoid conflicts | Merge conflicts | Full CI; the diff is whitespace-only (`git diff -w --stat` is empty for Python) | S + review |
| 4.2 | Split `routes.py` | `caf_api/routes.py` → `study.py`, `profile.py`, `system.py`; shared `deps.py` (`get_db`, `get_operations_db`, `get_identity_db`, `get_curation_db`) | Move the handlers unchanged. Move `approved_source` and `current_question` into `caf_api/published.py` to break the `questions`↔`published_pages` import cycle. Remove the in-function imports | Route order (SPA catch-all must stay last) | OpenAPI drift check (0.4) shows an identical schema; full pytest | M |
| 4.3 ∥ | Constants out of code | `auth.py:207-208`, `settings.py:13`, `routes.py:147`, `QuestionReader.tsx:28` | New-account defaults come from the active target-attempt binding (`caf_l5/context.approved_binding`), falling back to `config/settings.toml`. Usable-exam families move into `config/sources.toml`. The applicability notice comes from `extraction_quality.baseline` metadata (already present in the payload) instead of a hard-coded P5 and May 2027 | Wrong default for new invitees | Tests for invitation binding, and a UI spec | S–M |
| 4.4 ∥ | Frontend hygiene | 16 relative imports of `packages/workspace`, `lib/data.ts:6-9`, the large pages | Import `@caf/workspace` by package name (add `exports` to its `package.json`). Replace `contextGeneration` with `queryClient.invalidateQueries({queryKey: [...]})` on `caf-profile-changed`. Extract hooks and subcomponents from `ClassificationQueue.tsx`, `Extraction.tsx` and `Readiness.tsx` only where a change is being made anyway | Cache behaviour change | `pnpm type-check`; Playwright specs `student.spec.ts` (profile change) and `classification.spec.ts` | M |
| 4.5 ∥ | Dead code | `scripts/phase*` (14 unreferenced), `caf_l5/scoring.py:72` `recompute_legacy_scores`, legacy unit `TagSuggestion` path (see Part B) | Move the scripts to `scripts/archive/` with a README. For `recompute_legacy_scores`, first `rg` the tests; if only legacy tests use it, keep it until Part B Phase B5 decides the legacy path's fate. **Ask the owner before deleting anything they may still run by hand** | Removing a manual tool | Full pytest | S |
| 4.6 | Test layout by feature | `tests/` | When a test file is touched, move it into `tests/{auth,study,publication,classification,recovery,ops}/`. Never a big-bang rename | — | Same test count before and after (`pytest --collect-only -q | tail -1`) | ongoing |
| 4.7 ∥ | Version identity | `main.py:38`, `packages/*/pyproject.toml` | The FastAPI `version` reads `importlib.metadata.version("ca-final")`. Leave the workspace member versions alone, but document that the root version is authoritative | — | `/api/v1/openapi.json` reports `0.2.x` | S |

## Phase 5 — Documentation

| Step | Goal | Approach | Effort |
|---|---|---|---|
| 5.1 ∥ | Accurate README | Rewrite around reality: what it is, roles (student/curator/admin), production = Compose on Ubuntu with Auth0 and Tailscale, local dev = `setup.py`, what is shipped vs pending. Link `docs/Home_hosting.md`. Remove the confetti, auto-save, 264-node and "later phases" claims | S |
| 5.2 ∥ | Docs archive | `git mv` phase evidence (`docs/Phase*`, `*_Verification.json`, screenshots) to `docs/archive/` with an index. Keep runbooks at the top level. Mark one plan current, and add a "superseded" banner to the other two | S |
| 5.3 ∥ | Architecture overview | `docs/Architecture.md`: package layers, request→role→schema map, data model diagram (mermaid), and the publication pipeline (reuse §1 of `REVIEW.md` plus Part B) | S |

---

# Part B — Agent-ready question association

## B0. How association works today (from the code)

There are **two generations** of the flow.

**Legacy, unit-level (still in the CLI):** `caf classify run` (`caf_cli/classify.py:86-145`) → `ClassificationPipeline.run_classification` (`caf_l3/pipeline.py:41-268`).
1. It selects gradable, current units of confirmed, verified s2023 Final documents (`pipeline.py:61-110`).
2. `TextbookClassifier.classify_unit` (`caf_l3/textbook.py:33-140`) gets the eligible candidates of the active taxonomy release (`caf_l0/releases.eligible_candidates`, all papers for P6) with their `DescriptorRevision`s. It then either calls Gemini (`caf_l3/llm.py:139-301`, prompt `textbook-v1`, structured JSON, model fallbacks, budget cap, `ops.llm_call` logging) or matches descriptor terminology and exclusion terms, where an ambiguous match becomes `needs_review`.
3. Results are written to `ingest.tag_suggestion` (primary/secondary rows, bucket, evidence) or `ingest.taxonomy_gap`, and `unit.classify_status` is updated. It commits per unit, stops on a quota error, and keeps going after other errors.

Confidence and bucket are **self-reported by the model and uncalibrated** (`"uncalibrated": True` throughout).

**Current, whole-question ("root") batch flow, which feeds publication:**
1. **Freeze inputs.** `export_batch` (`caf_l3/batches.py:133-185`) builds a manifest per reviewed, current extraction revision. Each record holds the complete question context (stem, parts, answers) and `classification_part_ids`. Candidates come from `candidate_evidence` (`:99-131`: descriptor, path, textbook references, hashes), narrowed to the top 40 by `retrieve_candidates`, a fixed lexical retrieval (`:37-55`, `retrieval="lexical-v1"`). There is a per-record `input_hash` and a manifest `batch_key` (content-addressed idempotency). The classifier identity is `method="codex"`, `model_id="gpt-6-luna"`, `prompt_version="root-classification-v1"` (`:27-28`).
2. **Execute (outside the DB).** Executors write one result file per question:
   - `run_operator_batch` (`:292-443`) runs `codex exec --sandbox read-only --model …` per record, with no DB access or credentials, under a lock file and with resumable `state.json`.
   - `caf_l3/openrouter.py`: free OpenRouter models, review files only, "without queue writes".
   - `caf_l3/paper_workers.py`: "Luna" full-paper workers.
   - The output schema is `RootOutput`/`MappingOutput` (`batches.py:58-96`), with enum-restricted candidate IDs per record (`output_schema`).
3. **Validate and import.** `caf classify import` (`caf_cli/classify.py:61-84`) → `import_batch` (`batches.py:238-289`). It re-checks the manifest and input hashes, re-exports to detect stale evidence, and applies `validated_mappings` (`:198-235`): every part mapped exactly once, labels within candidates and paper, per-label evidence, and unresolved outcomes carry no labels. It then appends an immutable `ingest.suggestion_revision` (unique `batch_key, question_id, input_hash`; `models/classification.py:31-48`) with full provenance. This runs on the `operations` DB role.
4. **Human review.** The curator UI `ClassificationQueue.tsx` → `GET /api/v1/curate/classifications` (`caf_api/curate.py:217-287`, `curation` role, any signed-in account; blind mode for benchmarks) → `POST /classifications/{id}/review` or admin `POST /classifications/bulk` → `review_classification` (`caf_l4/revisions.py:348-394`). That function checks idempotency (`classification_event`, unique `actor_id, idempotency_key`), optimistic concurrency (expected suggestion and publication revisions), readiness gates (`readiness`, `:81-155`), unresolved parts and open disputes. It then writes `core.classification_revision` plus a verification. Blind reviews are stored as evidence only (`blind=True`) and never published.
5. **Publish and use downstream.** `project_question` (`caf_l4/questions.py`) creates `core.published_question`. `_project_appearances` (`revisions.py:264-337`) writes `core.decision`, `core.appearance` and `appearance_tag`, and sets `unit.classify_status`. `core.question_publication` points to the current revision. Verify, dispute and resolve live in `revisions.py:408-510`. Intelligence (`caf_l5/scoring.recompute_scores`) reads published questions, and the student app reads `/api/v1/questions*`, the subtopic detail and the scores.
6. **Evaluation.** `evaluate_model_on_reviewed_decisions` / `evaluate_revision_pairs` (`caf_l3/evaluate.py:43-145`) compare frozen suggestions with **blind** human revisions on identical `input_hash` and context, de-duplicated with `sampling.duplicate_key`. Metrics: top-1, outcome agreement, multilabel P/R, bucket precision, candidate-retrieval misses, strata. The gate is ≥30 Bucket-A roots at ≥0.80 precision, and "never authorizes publication". `caf_l3/sampling.stratified_sample` freezes dev/test splits; `artifacts/phase5/*` holds pilot samples and labels.

**Not verified / unsure:** whether the legacy `tag_suggestion` path still feeds any live screen (the curator `Queue.tsx`/`BulkAccept.tsx` pages may still use it); how many blind gold labels exist in production; whether `codex` exists on `caf-home` (it is clearly an operator-workstation tool).

## B1. Design overview

```
POST /api/v1/association/jobs ──► ingest.association_job + association_item (validated, frozen inputs)
                                         │  (lease, SKIP LOCKED — same pattern as intel.recompute_job)
                                caf classify worker ──► AssociationEngine (registry: lexical | gemini | openrouter | agent…)
                                         │  RootOutput  ──► validated_mappings()  (existing)
                     ┌───────────────────┴────────────────────┐
         mode=review (referenced items)              mode=evaluation (inline or referenced)
   import_record() → ingest.suggestion_revision      result stored on association_item only
   → existing curator queue / bulk review / publish  → metrics vs frozen eval set
```

The design reuses what already exists: the manifest record format and `input_hash` (`export_batch`), the output contract (`RootOutput`), validation (`validated_mappings`), the immutable store (`SuggestionRevision`), content-addressed candidate catalogs (`ref.candidate_catalog`), job leasing (`caf_l5/jobs.py` pattern), the run and LLM-call audit (`open_run`, `ops.llm_call`) and the evaluation logic (`evaluate_revision_pairs`). The API contract is new, but everything behind it is today's logic moved behind an interface.

## B2. Swappable engine interface

New package module `packages/l3_classify/caf_l3/association/`:

```python
class EngineInfo(BaseModel):          # recorded on every item
    name: str                         # "lexical", "gemini", "openrouter", "agent"
    version: str                      # semver of the adapter code
    prompt_version: str | None
    prompt_sha256: str | None         # hash of the exact system prompt template
    model_id: str | None
    config_hash: str                  # hash of engine config (thresholds, retrieval, limits)
    calibrated: bool                  # True only after B6 gate passes for this exact config_hash
    network: bool                     # needs egress/credentials

class AssociationEngine(Protocol):
    info: EngineInfo
    def associate(self, record: AssociationRecord) -> EngineResult: ...
    # record = existing manifest record shape (question_id, context, candidates, input_hash)
    # EngineResult = RootOutput-compatible dict + usage (tokens, cost, latency) + raw_output (for audit)

class EngineError(Exception): retryable: bool  # QuotaExceeded(retryable, pauses job), InvalidOutput(retryable once), Permanent
```

Adapters (each a thin wrapper, with no behaviour change to the wrapped logic):
- `LexicalEngine`: the terminology/exclusion logic from `textbook.py:80-113`, lifted into a pure function that maps root parts and produces a `RootOutput`. No network. It is the default and the only engine enabled in production unless the owner opts in.
- `GeminiRootEngine`: today's `GeminiClassifier` call (budget, fallbacks, retries, `ops.llm_call`), with the prompt adapted to root records and the `output_schema(record)` enum constraint.
- `OpenRouterEngine`: wraps `openrouter.classify_record`.
- The Codex operator **stays a CLI executor**, because it needs the `codex` binary and an operator workstation. Its result files still enter through `caf classify import`, refactored to share `import_record` (B4).
- Future `AgentEngine`: any multi-step tool-using workflow, as long as it returns the same `EngineResult`. Its tools get **read-only** access to the candidate list in the record. It never receives DB credentials, matching the Codex sandbox principle.

`engines.toml` (or a `[association]` section in `config/models.toml`) holds the registry: enabled engines, per-engine rate limit (requests/min), budget per job, thresholds. The API accepts only an engine name that is enabled in the registry.

**Trade-off:** the engine sees one root question at a time. That matches today's root contract and keeps failure isolation per question. Full-paper context (as the Luna paper workers use) is lost. An agentic engine can still batch internally if it declares `batch_capable`, but it must return per-question results.

## B3. Data model (migration `0011_association_jobs`, additive)

`ingest.association_job`
- `id uuid pk`, `actor_id → app.user_account`, `idempotency_key text`, `request_hash text`. Unique `(actor_id, idempotency_key)`.
- `mode text check in ('review','evaluation')`, `engine_name`, `engine_info jsonb` (frozen at creation), `taxonomy_release_id → ref.taxonomy_release`, `taxonomy_version_id`, `taxonomy_manifest_hash`, `candidate_catalog_hash → ref.candidate_catalog` (nullable; set for an inline tree), `eval_set_id` (nullable).
- `status check in ('queued','running','paused_quota','completed','completed_with_failures','cancelled','failed')`, plus `counts jsonb` (pending/running/auto_accepted/needs_review/failed), `run_id → ops.run`, `budget_usd`, `spent_usd`, `created_at`, `started_at`, `finished_at`.

`ingest.association_item`
- `id bigint pk`, `job_id → association_job`, `position int`, unique `(job_id, position)`, unique `(job_id, question_id)` where `question_id` is not null.
- `kind check in ('reference','inline')`; `question_id`, `extraction_revision_id` (reference); `inline_input jsonb` (inline only, size-checked).
- `record jsonb` (frozen engine input = the manifest record), `input_hash`.
- `status check in ('pending','running','auto_accepted','needs_review','failed','cancelled')`, `attempts`, `next_attempt_at`, `lease_until`, `lease_token`, `last_error_code`, `last_error`.
- `raw_output jsonb`, `mappings jsonb` (validated), `confidence numeric` (minimum over parts), `usage jsonb`, `suggestion_revision_id → ingest.suggestion_revision` (review mode), `created_at`, `finished_at`.
- Index `(status, next_attempt_at)` for claiming; index `(job_id, status)` for results.

`ingest.association_eval_set` / `association_eval_item` (B6): frozen gold sets. `id`, `name`, `taxonomy_version_id`, `content_hash`, plus items referencing blind `core.classification_revision` IDs and their `input_hash`.

**Grants** (`caf_db/grants.py`): no new role. The API creates jobs and reads results on the **operations** role. Admin endpoints already use it (`curate.py:57`). The worker uses operations (it already has full `ingest/core/ops`). `caf_curator` gets `SELECT` on both tables so the review queue can show job provenance. `caf_app` gets no access. Both tables are covered by the existing role-separation tests in `tests/test_isolation.py` / `test_phase2_database.py`.

**Data safety:** new tables only. `suggestion_revision.provenance` gains `association_job_id` and `engine` keys (JSONB, no column change). Existing rows stay untouched.

## B4. Processing semantics

- **Creation (synchronous, in one transaction):** validate the request, resolve the taxonomy release and check `manifest_hash`. For referenced items, call a refactor of `export_batch` → `build_records(session, release, items)`, which returns per-question records **or per-item validation errors** instead of raising for the whole batch. Items that fail validation are stored as `failed` with `last_error_code` (e.g. `extraction_not_current`, `no_gradable_parts`, `unknown_question`). The rest are `pending`. Return `202` with the job.
- **Worker:** `caf classify worker` (new Compose service, same image, `operations` role). It is on the `egress` network only when a network engine is enabled; otherwise backend only. Loop: claim up to N pending items `FOR UPDATE SKIP LOCKED` (lease 300 s, the `caf_l5/jobs.claim_job` pattern), respecting each engine's token-bucket rate limit, then call the engine.
- **Per item, isolated:** the engine call → `validated_mappings(record, result)` → status. A failure updates only that item, and the job continues. Retries: `retryable` errors back off exponentially (30 s, 2 min, 10 min) up to `max_attempts=3`, then `failed`. `InvalidOutput` (schema or validation failure) is retried once, then `failed` with the raw output kept. `QuotaExceeded` returns the item to `pending` and sets the job to `paused_quota` with `next_attempt_at`; it does not fail items (this matches today's `QuotaExhaustedError` behaviour). The budget cap (`budget_usd`) stops claiming new items; the remaining items stay `pending` and the job pauses. A crash is recovered by lease expiry.
- **Status assignment:**
  - `failed`: no valid output after retries.
  - `needs_review`: any part has an outcome `needs_review`/`none_fits`, any part has bucket ≠ A, any part has confidence < `threshold` (default 0.85), or `engine.calibrated` is false.
  - `auto_accepted`: every part `matched`, confidence ≥ threshold, and the engine's exact `config_hash` has passed the B6 gate.

  Consequence (intended, and honest): **until an engine is calibrated, nothing is auto-accepted.** Today every engine is uncalibrated.
- **Review mode, after a valid output:** `import_record(session, record, result, run_id, provenance)` is extracted from `import_batch` (`batches.py:238-289`), so it is the same stale-evidence check and the same immutable `SuggestionRevision` insert (idempotent on `batch_key, question_id, input_hash`). The job's `batch_key` is `digest({engine_info, taxonomy, records})`, so re-running identical inputs and engine reuses the existing suggestion rather than duplicating it. `failed` items never create suggestions.
- **Into the existing human path:** the queue `GET /curate/classifications` gains filters `association_job_id` and `association_status`. `ClassificationQueue.tsx` adds a "Pre-approved (auto-accepted)" filter and a "Confirm all pre-approved on this page" action, which calls the **existing admin `POST /classifications/bulk`** with per-item `expected_*` revision IDs and idempotency keys. The readiness gates, disputes and verification rules all still apply. `needs_review` items appear as normal suggestions.
- **Audit:** each item keeps the frozen `record` (input), `raw_output`, validated `mappings`, `engine_info` (name, version, prompt version and SHA-256, model, config hash), usage and cost, attempts and errors. The job links to `ops.run` (via `open_run`) and `ops.llm_call` rows. The human decision is in `classification_event`/`classification_revision` (existing). Together this answers "who/what decided, on which input, with which logic version".
- **Cancellation:** `POST …/cancel` sets pending items to `cancelled`; running items finish.

## B5. API contract

All endpoints use `require_admin` (they spend model budget and change curation state; consistent with `/classifications/bulk` and `/baselines/*`). They inherit the cookie session, CSRF and Origin checks from `require_account`. Router: `packages/api/caf_api/association.py`. Contracts: `packages/contracts/caf_contracts/association.py`.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/association/engines` | Enabled engines with `EngineInfo`, limits, and calibration status |
| `POST /api/v1/association/jobs` (header `Idempotency-Key`, required, ≤ 128 chars) | Create a job → `202 {job}`. A repeated key with the same `request_hash` returns the original job (`200`); a different hash returns `409 idempotency_conflict` |
| `GET /api/v1/association/jobs?status=&cursor=` | List jobs |
| `GET /api/v1/association/jobs/{job_id}` | Status and counts |
| `GET /api/v1/association/jobs/{job_id}/results?status=&cursor=&limit≤100` | Per-question results (cursor = item position) |
| `POST /api/v1/association/jobs/{job_id}/cancel` | Cancel pending items |
| `POST /api/v1/association/eval-runs` / `GET …/{id}` | B6: run an engine over a frozen eval set; returns a metrics report |

**Validation and limits** (Pydantic `extra="forbid"`, plus a request-body size middleware):
- Body ≤ 1 MB (≤ 5 MB with an inline tree).
- 1–100 items per job (≤ 50 inline).
- Inline `question_text` ≤ 20 000 chars, `answer_text` ≤ 40 000 chars, parts ≤ 30.
- Inline tree ≤ 3 000 nodes and depth ≤ 6, with unique IDs, one root per paper, and `level` in the known levels.
- `mode=review` requires every item to be `kind=reference` and the syllabus to be a reference (otherwise `422 inline_not_reviewable`).
- At most 2 active jobs per admin, and job creation limited to 10/hour per principal (2.9 limiter).
- The engine must be enabled. Network engines require explicit registry enablement.

**Request example (review mode):**
```json
{
  "mode": "review",
  "engine": "lexical",
  "syllabus": { "kind": "reference", "taxonomy_release_id": "textbook-2026-10", "manifest_hash": "sha256:9c1e…" },
  "items": [
    { "kind": "reference", "question_id": "rtp-p1-nov2026-q11", "extraction_revision_id": 412 },
    { "kind": "reference", "question_id": "mtp-p3-may2026-q2" }
  ],
  "options": { "auto_accept_threshold": 0.85, "budget_usd": 0 }
}
```

**Request example (evaluation, inline):**
```json
{
  "mode": "evaluation",
  "engine": "agent",
  "syllabus": { "kind": "inline", "paper_id": "s2023.P1",
    "nodes": [ { "id": "P1-CH05", "parent_id": null, "level": "chapter", "name": "Ind AS 116 Leases" },
               { "id": "P1-CH05-S2", "parent_id": "P1-CH05", "level": "subtopic", "name": "Lessee measurement",
                 "descriptor": { "terminology": ["right-of-use asset", "lease liability"], "exclusion": [] } } ] },
  "items": [ { "kind": "inline", "client_ref": "q-001", "paper_id": "s2023.P1",
               "question_text": "…", "answer_text": "…", "parts": [] } ]
}
```
An inline tree is normalized into the existing candidate shape (`candidate_evidence` fields) and stored content-addressed in `ref.candidate_catalog`.

**Response (`GET …/results`):**
```json
{
  "job_id": "5f0c…", "status": "completed_with_failures",
  "engine": { "name": "lexical", "version": "1.0.0", "prompt_version": null, "model_id": null,
              "config_hash": "sha256:…", "calibrated": false },
  "items": [
    { "position": 0, "question_id": "rtp-p1-nov2026-q11", "status": "needs_review", "attempts": 1,
      "input_hash": "sha256:…", "suggestion_revision_id": 9182,
      "parts": [ { "part_id": "rtp-p1-nov2026-q11", "outcome": "matched",
                   "primary_node_id": "P1-BXTF71", "secondary_node_ids": [],
                   "confidence": 0.62, "bucket": "B",
                   "reasoning": "Matched reviewed descriptor terminology: 'right-of-use asset'.",
                   "evidence": { "P1-BXTF71": "…" } } ] },
    { "position": 1, "question_id": "mtp-p3-may2026-q2", "status": "failed", "attempts": 0,
      "error": { "code": "extraction_not_current", "message": "Reviewed current extraction required" } }
  ],
  "next_cursor": null
}
```
`reasoning` maps to the existing `MappingOutput.note` (or `justification` for the legacy path). The `parts[]` shape is today's validated mapping, renamed only at the API boundary.

## B6. Evaluation set and metrics

- **Gold set:** frozen from existing **blind** `core.classification_revision` rows (`blind=True`) plus their `SuggestionRevision.context` and `input_hash`. `caf classify eval-set freeze --name …` uses `sampling.stratified_sample` and `duplicate_key` for de-duplication and dev/test splits, and stores it in `association_eval_set` with a content hash. `artifacts/phase5/independent30_labels.json` may seed it (**unsure** whether those labels are bound to current `input_hash`es; the freeze step reports how many are still valid).
- **Run:** an eval run executes an engine in `mode=evaluation` over the set's frozen records. Results are stored as items; nothing enters the queue.
- **Metrics:** reuse `evaluate_revision_pairs` (top-1 primary accuracy, outcome agreement, multilabel precision/recall, bucket precision, candidate-retrieval misses, strata). Add: expected calibration error (10 bins on part confidence), a coverage-vs-precision curve at thresholds 0.5–0.95, failure rate, mean latency, and cost per question. The report is keyed by `engine.config_hash`.
- **Gate (sets `calibrated=true` for that exact `config_hash`):** the existing rule (≥30 independent roots, Bucket-A precision ≥0.80, not provisional), **plus** precision at the chosen auto-accept threshold ≥0.90 on the held-out test split. A new engine (agentic) is "proven" when it beats the current engine on top-1 and multilabel F1 on the same frozen set without a worse calibration error. **Unsure:** whether enough blind gold exists today to reach 30 roots per paper. The first deliverable of B6 is a count, and if it is short, a blind-review campaign using the existing `blind=true` review mode.
- **Admin view:** `/curator/system` gets an "Association engines" panel comparing reports side by side.

## B7. Rollout (today's workflow keeps working throughout)

| Step | What | Keeps working | Verify | Effort |
|---|---|---|---|---|
| B1 | **Refactor only.** Add `association/engine.py`, `LexicalEngine`, `GeminiRootEngine`. Extract `build_records` and `import_record` from `export_batch`/`import_batch`, with `export_batch`/`import_batch` becoming thin wrappers over them | `caf classify export/import/operator-run/run` unchanged | **Golden tests**: identical manifests, `batch_key`s and imported rows before and after on the fixtures in `tests/test_phase5_batches.py`, `test_phase3_classification.py`, and `profiles/fixtures/*` | M |
| B2 | Migration `0011`, plus grants and the restored-snapshot migration test | Everything (additive) | `tests/test_migration_baseline.py` pattern; grants tests | M |
| B3 | Jobs API + worker in **evaluation mode only**, behind a `ASSOCIATION_API_ENABLED` setting (off in production) | Review queue untouched | API tests: validation and limits, idempotency (same/different hash), cancellation, rate limit, per-item failure isolation (inject an engine that fails item 2 of 3), retry and backoff with a fake clock, lease recovery after a simulated worker crash, quota pause/resume, budget stop. Engines are faked in tests (network disabled by `conftest.py`) | L |
| B4 | Eval sets and metrics (B6); the lexical baseline report | — | Unit tests for the metric math on handcrafted pairs; freeze is deterministic (same hash twice) | M |
| B5 | **Shadow:** for real batches, create the same records through both the CLI export and the API job (lexical engine); compare `input_hash` and `mappings` | The CLI remains the path of record | A comparison report shows 100% `input_hash` equality | S |
| B6 | Enable `mode=review` (admin). Add queue filters and "confirm pre-approved" UI using the existing bulk endpoint | The CLI import path is still available; humans still confirm everything | Playwright spec: job → queue → bulk confirm → published question visible in the student reader; `blind` mode still hides provenance | M |
| B7 | Production enablement: install through `caf-host upgrade` (Phase 1), lexical engine only, with owner authorization. A network engine needs a separate explicit owner decision (paid calls) | — | Readiness; one small real job; recovery snapshot taken before the upgrade | S |
| B8 | Agentic engine: implement `AgentEngine`, evaluation-only, until it passes the B6 gate and beats the baseline; then the owner enables it for `review` | Lexical/Gemini remain selectable | Eval report comparison | L |
| B9 | Decide the fate of the legacy unit-level `tag_suggestion` path once nothing reads it (check `Queue.tsx`/`BulkAccept.tsx` and `/curate/queue` usage first). Deprecate, don't drop the tables | Historical rows preserved | — | S |

## Overall order and parallelism

1. **Phase 0** (all steps ∥).
2. **Phase 1** (1.1 → 1.2 → 1.3), with **Part B B1** in parallel (pure refactor, different files) and Phase 2's non-migration steps (2.2–2.5, 2.7, 2.9, 2.12, 2.13) in parallel.
3. **Phase 2** migration `0010` (2.1 + 2.6) and 2.8, 2.10, 2.11.
4. **Phase 3** ∥ **Phase 5**. Then **Part B B2–B4**.
5. **Phase 4.1** (formatting) in a quiet window with no other branches open, then 4.2–4.7.
6. **B5 → B9.**

The first production install happens after Phase 1 is accepted and bundles Phase 0 plus 2. Each later release goes through `caf-host upgrade`.

## Verification (end to end, per release)

- CI: pytest (real Postgres), ruff, mypy subset, OpenAPI drift, dist sync, `pnpm type-check`/`test:ui`/`build`, Playwright.
- Before install: build the candidate bundle (`scripts/release_bundle.py build --candidate`) and run `scripts/verify_production_stack.py` on an isolated stack, covering upgrade from the previous bundle, table-digest preservation, and readiness.
- On `caf-home` (only with owner authorization): `caf-host upgrade`, `/api/v1/ready`, signed-in browser smoke test (study workspace, question reader, PDF page, curator queue), backup timer status, and the alert test.
- Part B specifically: one lexical job of about 10 referenced questions → results endpoint → queue → bulk confirm → student reader shows the published mapping; then an eval-run report for the lexical baseline.

## Open uncertainties (to resolve inside the named steps)

- Which Playwright specs can run headless in CI without Auth0 (0.3).
- Whether client IPs are distinguishable behind Tailscale serve (2.9).
- Whether any existing notes exceed the proposed limits (2.1; it is measured, never truncated).
- How much blind gold data exists (B4).
- Whether the legacy `tag_suggestion` UI path is still used (B9).
- Whether Vite builds are deterministic enough for the dist check (0.5).
