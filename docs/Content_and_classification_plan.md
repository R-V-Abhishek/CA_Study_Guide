# Content and classification plan

Approved 2026-11-10. It supersedes Part B of [../PLAN.md](../PLAN.md).

Status (2026-11-10): **P0 done** (PR #40). **P1 implemented, not yet released or installed**: steps 1.1–1.6
are done ([Content_updates.md](Content_updates.md)); 1.7, the first real import, needs a release and the
owner's authorization. P2–P4 are not started.

Changes from the text below, made during P1:
- Provenance is derived from the bundled evidence (an HTTPS download from a `pdf_hosts` host), not copied
  from the curating database. New fetches are recorded `unresolved` there, so requiring `verified` would
  have refused every new PDF.
- An existing document is reported (with the catalogue fields that differ) and left unchanged, rather than
  aborting the whole import, so a snapshot that overlaps production stays importable.
- The archive has no creation time or builder commit, so the same documents give the same bytes.
- `caf-host content report` is left for P2.

## Context

Part A of `PLAN.md` has shipped (PR #10, #30). `docs/Code_review_2026_11_06.md` is fixed apart from L-06. v0.3.1 runs on `caf-home` (confirmed by the owner; the repo has no record of it). Production content is frozen at `baseline-2026-10-16`: 3,009 questions and 94 PDFs. **New PDFs have no supported path into production.** `caf-host` has no content command, and `AGENTS.md` forbids replacing production with a developer database. So new ICAI papers, suggested answers, RTPs and MTPs can't reach students. Part B's API, worker and job queue would only reclassify content that is already there.

Owner decisions:
- (q1-b) Content reaches production as **verified content snapshots**: a bundle with its own identity, separate from app releases and recovery snapshots.
- The snapshot carries **sources only**: PDF bytes, metadata and acquisition provenance, addressed by SHA-256. Derived data (extraction, classification) is produced **on production, with production IDs**. That avoids the internal IDs embedded in `ExtractionRevision.questions[].assets[].document_id`, `configuration.pairing`/`predecessor_document_id`, and the classification `input_hash` (which includes `document_id`, `extraction_revision_id` and `taxonomy_version_id`).
- Humans stay in the loop in the production UI: confirming metadata, pairing documents, reviewing and promoting extractions, and reviewing classifications. Nothing publishes without a human action.

Ground rules (unchanged): one `codex/<topic>` branch and PR per step, using Conventional Commits. Tests go in the same PR. `main` stays releasable. **P1 needs no migration.** Nothing touches `caf-home` without the owner's authorization for that action. No paid model calls.

---

## P0 — Make the record true (small, first)

1. **Record the v0.3.1 install.** With owner authorization, run read-only `caf-host status` on `caf-home` and add the receipt facts to a new `docs/Deployment_verification_2026_11_07.md` (or whatever date the receipt shows). Update:
   - `docs/Home_hosting.md`: the current checkpoint, and the "Pending incremental steps" list (backups and upgrade are done; external drive and off-host copy are pending; content updates are pending)
   - the `AGENTS.md` deployment handoff
   - `docs/Architecture.md`: §7 and §8 (the host scripts are now drill-tested; there is no content path yet)
2. **Retire the old plan.** Add a banner to `PLAN.md`: Part A done, Part B superseded. Then copy this plan to `docs/Content_and_classification_plan.md`.
3. **Triage Dependabot.** Read the failure logs of #34 (TypeScript 7), #36 (Vite 8), #37 (lucide 1.x) and #39 (google-genai 3).
   - Close the major bumps that need migration work, and add `ignore` rules for those majors to `.github/dependabot.yml`.
   - Merge the green groups (#33, #38) once CI passes.

Verify: a content check of the doc diffs; CI green on `main`.

## P1 — Content snapshots (the main feature; ships as v0.4.0)

### 1.1 Bundle format and builder (Mac): `caf content build`
- New module `packages/l1_acquire/caf_l1/content_bundle.py` and CLI `packages/cli/caf_cli/content.py`, registered in `caf_cli/main.py`.
- Input: an explicit list of document SHA-256s from the local database (`--sha` repeated, or `--from-file`). Output: `content-<snapshot_id[:12]>.tar.gz` plus `.sha256`.
- Members:
  - `manifest.json`: `schema_version`; `snapshot_id = digest(entries)` using `caf_l2.revisions.digest`; `created_at`; builder commit; and per-entry `sha256`, `bytes`, validated metadata, and an optional `pair_with` answer SHA-256 hint.
  - `sources/<sha>.pdf`
  - `observations/<sha>/*.json`, copied from the blob store's `acquisition/` evidence (written by `caf_l1.artifacts.record_observation`).
- Deterministic: sorted members, fixed mtime, owner and mode. Reuse the tar and streaming-hash helpers in `scripts/release_bundle.py` (move the shared parts into `caf_common` if they're needed from a package). Refuse documents whose `provenance_status` is not `verified` or whose blob hash doesn't match.

### 1.2 Verifier
`verify_content_bundle(path)` follows the release-bundle verify rules:
- stream and hash members without extracting paths
- reject links, duplicates, extra or missing members and absolute paths
- each PDF's hash must equal its name, and it must pass `caf_l1.artifacts.validate_pdf`
- metadata must pass `validate_metadata`
- `snapshot_id` must recompute

### 1.3 Importer: `caf content import ARCHIVE`
- Verify first. Then **one transaction, all or nothing**, under `open_run("content.import", {snapshot_id, archive_sha256})`.
- Per entry:
  - existing SHA-256 with the same metadata → `existing`
  - existing SHA-256 with different metadata → **conflict**: abort and report, never overwrite
  - otherwise insert with `catalog_status="needs_curation"`, put the bytes through `BlobStore.put`, and record the observations
- Refactor `caf_l1/importer.py` `ManualImporter.import_file` so it delegates to a new `import_bytes(data, meta, session, run_id)`. `import_file` keeps its behaviour; the content importer calls `import_bytes`. The `pair_with` hint goes in `metadata_evidence` only; pairing stays a human action (`POST /extraction/documents/{id}/pairs`).
- Re-running the same bundle is a no-op. The run stats record the imported, existing and conflict counts.

### 1.4 Host commands: `caf-host content {import|extract|classify-export|classify-import|report}`
- New `deploy/content-host.sh`, dispatched from `deploy/caf-host`. It reuses the patterns in `deploy/upgrade-host.sh`:
  - the `flock` deployment lock and an active-receipt check
  - `verify` in a `--network none --read-only --cap-drop ALL` container
  - a free-space check
- Put the hardened `docker run` flags and readiness probes in a new `deploy/lib.sh`, used by `content-host.sh` only. This is a start on L-06; the existing scripts move over later.
- Add a new Compose tools service `content` in `compose.production.yml`, modelled on `pipeline` but with **backend network only** (no egress) and the `operations` role. It mounts the bundle read-only and `/srv/caf/content/{outbox,receipts}` read-write. Update `scripts/verify_production_compose.py`.
- `import BUNDLE`:
  1. Take a recovery snapshot (`compose run web backup run` plus `_upgrade verify-snapshot`, as `upgrade-host.sh` does at lines 156–172).
  2. Run `compose run --rm content content import`.
  3. Write `/srv/caf/content/receipts/<snapshot_id>.json` (archive SHA-256, run ID, counts, recovery snapshot name, status).

  Services stay up: the import is additive, and the transaction rolls back on failure.
- `extract [--doc ID] [--limit N]`: runs `caf extract run --status pending --ocr` for **confirmed** documents. It takes a separate content lock, not the deployment lock, so the nightly backup isn't blocked.
- `classify-export` / `classify-import`: wrap the existing `caf classify export/import` (`caf_l3/batches.export_batch`/`import_batch`) against production. The manifest goes to `outbox/`. The operator runs the engine on the Mac (`caf classify operator-run` or the Luna workers), copies the results back, and imports them. The existing stale-evidence and immutable-revision checks apply unchanged.
- `report`: the read-only quality report (P2).

### 1.5 Production flow (documented, no new UI)
`caf-host content import` → admin confirms the metadata in the curator **Catalogue** (`POST /curate/documents/{id}/confirm`) → pair the documents → `caf-host content extract` → review and promote in **Extraction** (`/extraction/revisions/{id}/reviews`, `/promote`) → `classify-export`, run the engine off-host, `classify-import` → review and publish in the **Classification queue**. The runbook goes in new `docs/Content_updates.md`, linked from `Home_hosting.md`.

### 1.6 Tests
- `tests/test_content_bundle.py`:
  - building twice gives the same `snapshot_id` and archive hash
  - the verifier rejects a tampered PDF, an extra member, a symlink, a duplicate and a bad metadata value
  - import is idempotent; a metadata conflict aborts with zero rows written; an unknown `paper_id`/`attempt_id` is rejected
  - `import_file` behaviour is unchanged (existing `tests/test_phase4_acquisition.py`)
- `deploy/tests/test_host_content.py`: the script's argument and receipt handling.
- Extend the native-Linux drill `scripts/verify_host_upgrade.py`, which runs in the release-builder CI, with: import a two-PDF bundle, confirm, extract, re-import (a no-op), check that the receipt exists and the backup still passes.

### 1.7 First real use (owner authorization)
The first batch of new official PDFs (for example the Nov 2026 papers and suggested answers, once ICAI publishes them). Start with `--limit 1` to measure OCR time and memory on `caf-home` before running larger batches.

## P2 — Quality baseline of the existing corpus (runs alongside P1)

1. `caf classify quality-report`, read-only through the `backup` role, outputting JSON. Per paper:
   - unresolved parts (`none_fits`, `needs_review`)
   - publications with no student verification, and open disputes
   - **the number of blind classification revisions** (the gold-set size Part B depends on)
   - pending legacy `tag_suggestion` rows (for P4)

   Run it on production through `caf-host content report`.
2. A curation pass by the owner and students, using the existing queue filters (`outcome=`, `paper_id=`, `blind=true` for gold). Also review P5's May 2027 applicability. Code changes only if the report shows a real gap in the tools.

## P3 — Slimmed-down Part B: a swappable engine and offline evaluation

1. **Refactor only (old B1).** New module `caf_l3/association/engine.py` with `EngineInfo`, the `AssociationEngine` protocol and `EngineError` (as specified in `PLAN.md` §B2). Adapters: `LexicalEngine` (lifted from `caf_l3/textbook.py`), `GeminiRootEngine` (`caf_l3/llm.py`), `OpenRouterEngine` (`caf_l3/openrouter.py`), and the Codex operator (stays a CLI executor). Split `build_records`/`import_record` out of `export_batch`/`import_batch`, which become thin wrappers. **Golden tests:** identical manifests, `batch_key`s and imported rows on the fixtures in `tests/test_phase5_batches.py` and `tests/test_phase3_classification.py`.
2. **Offline evaluation (old B4/B6, without the tables).**
   - `caf classify eval-set freeze` writes a content-hashed JSON file of blind revisions plus their frozen records and gold mappings, with dev/test splits (`caf_l3/sampling.stratified_sample`, `duplicate_key`).
   - `caf classify eval run --engine X --set FILE` runs with no database.
   - Metrics reuse `caf_l3/evaluate.evaluate_revision_pairs`, plus expected calibration error, coverage against precision, failure rate, latency and cost. Reports are keyed by `config_hash`.
3. **Explicitly deferred:** the HTTP jobs API, the worker and leasing, migration `0011`, auto-accept, inline syllabus trees and the "Association engines" panel. Revisit them when content volume or a calibrated engine justifies it.

## P4 — Retire the legacy unit-level queue (old B9, brought forward)

The P2 report must show no pending legacy work. Then, **with owner confirmation**:
- remove the `/curator/queue` and `BulkAccept` routes and navigation (`web/apps/curator/src/App.tsx`)
- remove the endpoints `GET /curate/queue`, `POST /curate/units/{id}/decision` and `/documents/{id}/bulk_accept_bucket_a` (`caf_api/curate.py`)
- regenerate `openapi.json` and the API client

Keep the `ingest.tag_suggestion` tables and history. Decide whether `caf_l5/scoring.recompute_legacy_scores` stays.

## Order

P0 → P1 (1.1–1.3, then 1.4, 1.6, 1.5; release v0.4.0 and install through `caf-host upgrade` with authorization) ∥ P2.1 → 1.7 first real import → P3 → P4.

## Verification

- CI: `uv run --no-sync pytest -q tests deploy/tests`, `scripts/verify_production_compose.py`, ruff, mypy, `pnpm type-check`/`test:ui`/`build`, Playwright, OpenAPI drift (P4).
- Release builder: the native-Linux upgrade drill, now including content import, extract and re-import.
- On `caf-home` (authorized): `caf-host upgrade` to v0.4.0 → `caf-host content import` of a small real bundle → receipt and recovery snapshot exist → Catalogue confirm → `content extract --limit 1` → the extraction shows in the curator UI → a classify export/import round trip → a reviewed question appears in the student reader → readiness passes and the nightly backup still succeeds.
- `git diff` reviewed for scope and secrets. `graphify update .` after code changes.

## Risks and open points

- OCR load and duration on `caf-home` (measured with `--limit 1`; the `content` service has CPU and memory limits).
- The extraction debug output path (`data/debug`) on a read-only container: pass no debug directory on the host, or write under `/srv/caf/data`.
- Extraction profiles for any new document type (profiles ship in the image under `profiles/` and `overrides/`).
- Whether enough blind gold exists for P3 evaluation (P2 measures it).
