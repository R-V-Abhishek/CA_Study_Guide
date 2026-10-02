# System Verification Checklist

Use this checklist to verify that your CA Final Study Companion is functioning correctly from infrastructure to user interface.

The architecture now targets invited students with private records, shared curation,
one-student publication, and distinct-student verification of specific revisions and
scopes. Authenticated readers will receive complete published questions and answers.
May 2027 is the future profile default; edition applicability and historical coverage
remain separate. Official taxonomy structure includes paper-specific exceptions, and
scores match the target/version context. Phase 0 preserves current application behavior.

## Phase 0 acceptance gate

The 2026-10-01 gate results and local artifact links are recorded in
[Phase0_Verification.md](docs/Phase0_Verification.md).

Execute these checks in order. A checked item requires actual evidence; this document
does not mark later authentication or reader work complete.

1. **Isolated harness:** `uv run pytest` bootstraps PostgreSQL 16 on a dynamically
   allocated localhost port before application imports. Verify normal application URLs
   and non-allowlisted admin/restore targets are rejected. Each database-changing test
   gets an independently seeded clone and temporary storage; external model/acquisition
   calls are disabled. Test roles/grants must exist and permission tests require SQLSTATE
   `42501`. Run representative tests individually to establish order independence.
   Use the active Docker context; on this workstation, start Colima with `colima start`
   if needed. The harness never mounts the application Compose volume.
2. **Synthetic recovery:** verify successful backup/restore and explicit failures for
   corrupt/unreadable dumps, restore errors, missing tables, and changed/missing archived
   files. Verify progress, notes, study sessions, decisions, and appearances. Change the
   source after backup and confirm verification still matches the snapshot manifest.
   An existing scratch destination must be rejected and preserved.
3. **Frozen baseline:** migrate an empty isolated database using the explicit
   `0001_initial_schema` operations. Compare tables, indexes, constraints, and foreign
   keys with the expected baseline. Subsequent changes require forward migrations.
4. **Read-only provenance:** run `uv run caf audit baseline`. Inspect timestamped JSON
   and Markdown reports under the ignored audit directory. Require explicit evidence
   for confirmed/suspected synthetic, authentic source identified, and unresolved records.
   Check source checksums, lineage, answers, published-unit links, questionable suggestions,
   score context, and descriptor gaps. Record missing reviewer identity without inventing
   a student assignment. Confirm no source-database writes.
   For preservation evidence after testing, run
   `uv run caf audit baseline --checkpoint-manifest <checkpoint-directory>/manifest.json`.
   The report compares
   UTC-normalized counts and digests of every `app`/`core` table; differences fail.
5. **Real recovery checkpoint:** create a unique backup using the existing CLI and
   independently verify it in a separate disposable container. Require the manifest,
   database revision, dump checksum, table counts/digests, archived source/configuration
   checksums, and machine-readable verification report. Compare its restored schema to
   the frozen baseline; resolve drift before later migrations. Do not rotate/delete
   existing checkpoints. Legacy backups cannot claim manifest-based content verification.
   Use `uv run caf backup run` and then
   `uv run caf backup verify --dump-file <reported-dump-path>`; retain the reported
   manifest and verification report with the checkpoint.
   Verification also creates a fresh migrated database and records
   `baseline_schema_drift`; `{}` means the restored schema agrees.
6. **Compatibility and diff:** run the full isolated suite and
   `uv run pytest tests/test_future_contracts.py`. Review all changes for production data,
   schema, endpoint, or configuration changes outside Phase 0. Future model tests establish
   representability, ordering, owner/revision consistency, and distinct scoped counts.
   Authentication/enforcement tests belong to Phase 2; reader tests belong to Phase 6.

Phase 0 passes only with the isolated suite, verified real checkpoint, provenance
reports, schema agreement, and aligned documents/contracts. The remaining checklist
describes current local behavior and must be exercised on disposable data for writes.

---

## 1. Quick Smoke Test

After running `uv run start.py`:

- [ ] **Database Running**: Terminal shows `🐘 Ensuring PostgreSQL database is active...` without errors.
- [ ] **HTTP Health**: Visit `http://localhost:8000/api/v1/health` in your browser.
  - Expected response: `status="ok"`, the configured environment and existing target
    attempt. Phase 0 preserves the local target; future profiles default to `2027-05`.
- [ ] **Interactive API Docs**: Visit `http://localhost:8000/docs`. The Swagger UI renders all 30+ endpoints.
- [ ] **Student Web App**: Visit `http://localhost:8000`. The Dashboard renders with summary cards and paper grid.
- [ ] **Curator Web App**: Visit `http://localhost:8000/curator`. The Curator Workbench loads with sidebar navigation.

---

## 2. Taxonomy & Reference Data Verification

- [ ] **Subtopics API**: Visit `http://localhost:8000/api/v1/subtopics?limit=5`.
  - Returns a JSON array with Crockford base32 ID format (`P[1-6]-[0-9A-Z]{6}`).
- [ ] **Total Syllabus Nodes**: Run `uv run caf taxonomy load`.
  - Current seed: 6 Papers, 39 Chapters, 77 Topics, 264 Subtopics. These counts are not
    certification of official syllabus completeness; the source/taxonomy audit is Phase 3.
- [ ] **Papers Overview**: In the Student App, click **Papers** in the navigation.
  - All 6 papers are listed:
    - `P1`: Financial Reporting
    - `P2`: Advanced Financial Management
    - `P3`: Advanced Auditing and Professional Ethics
    - `P4`: Direct Tax Laws & International Taxation
    - `P5`: Indirect Tax Laws
    - `P6`: Integrated Business Solutions
- [ ] **Interactive Tree Navigation**: Click any paper (e.g. `P1`).
  - Left pane displays Chapter/Topic hierarchy.
  - Clicking a subtopic opens the right pane with Importance dots (`●●●●○`), weightage, and Markdown notes editor.

---

## 3. Student Study Tools Verification

- [ ] **Weekly Study Plan (`/plan`)**:
  - Click **Study Plan** in the top navigation bar.
  - Day-by-day timeline cards render.
  - Changing the weekly budget dropdown (15h, 20h, 28h, 35h) dynamically adjusts daily tasks.
  - Clicking **Regenerate Plan** refreshes the recommendations based on topic weightage.
- [ ] **Spaced Revision Queue (`/revision`)**:
  - Click **Revision** in the navigation bar.
  - Focused single-card recall mode renders.
  - Click **✓ Got it** — advances interval, plays confetti burst, and smoothly transitions to the next item.
- [ ] **Syllabus Progress Audit (`/progress`)**:
  - Click **Progress** in the navigation bar.
  - Overall progress bar and Group 1 / Group 2 completion meters render.
  - Click **Export CSV** button — downloads `ca_final_syllabus_progress.csv`.
- [ ] **Mock Test Tracker (`/mock`)**:
  - Click **Mock Tests** in the navigation bar.
  - Click **+ Log Mock Test Result** — fill in Paper, Series label, Score, and Max Marks.
  - The Recharts progression graph immediately updates showing your test trajectory.
- [ ] **Markdown Notes Auto-Save**:
  - In any subtopic detail view, type personal notes into the editor.
  - Observe indicator change: `Unsaved changes` → `Saving...` → `Auto-saved`.
  - Refresh the browser page — your notes persist.

---

## 4. Curator Workbench Verification

- [ ] **Review Queue (`/curator/queue`)**:
  - Displays pending extracted units with question and solution text side-by-side.
  - Suggested topic tags appear in the right panel with confidence badges (Bucket A, B, C).
  - Press `E` on keyboard — 264-node modal search pops up immediately.
  - Press `Escape` — modal closes.
- [ ] **Bulk Accept (`/curator/bulk`)**:
  - Lists documents with pending Bucket A consensus items.
  - Click **Bulk Accept** for any document — triggers atomic approval.
- [ ] **Document Catalogue (`/curator/documents`)**:
  - Shows ingested PDFs with SHA-256 deduplication hashes and page counts.
- [ ] **Taxonomy Browser (`/curator/taxonomy`)**:
  - Full syllabus tree with copy-to-clipboard buttons for Crockford node IDs.
- [ ] **System Health & Alarms (`/curator/system`)**:
  - Monitors all 5 operational alarms:
    - A1: Unclassified Spike
    - A2: Pipeline Failure
    - A3: Stale Scores
    - A4: Depth Gate Drift
    - A5: Unverified Document Alert
  - Click **Recompute Intelligence Scores** — triggers pipeline recomputation with a success confirmation banner.

---

## 5. Current Metadata Compatibility and Future Access Gates

- [ ] **Current Metadata Endpoint Compatibility**:
  - Open Student App network tab in browser developer tools.
  - Verify that no requests to `/api/v1/curate/*` are made from the Student App.
  - Verify that the existing metadata endpoints retain their response shapes without
    embedded question/answer text. Revised D2 allows complete published content through
    the future authenticated reader; this compatibility check is not a universal ban.
- [x] **Phase 2 isolated ownership gate**: two authenticated students cannot read or
  change each other's progress, notes, study sessions, settings, or exports. Every invited
  student may curate; administrative operations remain separately authorized.
  Python and Chromium/WebKit evidence is recorded in `docs/Phase2_Verification.md`.
  Real Auth0 invitation redemption, preserved owner profile and logout passed locally.
  Native Windows verification remains pending.
- [ ] **Phase 5/6 publication and reader gates (future)**: one student's review permits
  publication; counts use distinct students, scope, and exact content/classification
  revision. Published readers return complete questions/answers; unreviewed staging
  and other students' private records remain inaccessible. Test actual endpoints.
- [ ] **Zero Shared UI Components**:
  - Student app and Curator tool are independently bundled with separate stylesheets and assets.

---

## 6. Clean Shutdown & Data Preservation

- [ ] **Stop Command**:
  - Press `Ctrl+C` in the terminal running `start.py` (or run `uv run stop.py`).
  - Terminal prints confirmation that PostgreSQL container is stopped.
- [ ] **Data Persistence**:
  - Restart the app: `uv run start.py`.
  - All previously entered study notes, progress marks, and mock test scores remain intact.
