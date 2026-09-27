# System Verification Checklist

Use this checklist to verify that your CA Final Study Companion is functioning correctly from infrastructure to user interface.

---

## 1. Quick Smoke Test

After running `python start.py`:

- [ ] **Database Running**: Terminal shows `🐘 Ensuring PostgreSQL database is active...` without errors.
- [ ] **HTTP Health**: Visit `http://localhost:8000/api/v1/health` in your browser.
  - Expected response: `{"status":"ok","env":"development","target_attempt":"2026-05"}`
- [ ] **Interactive API Docs**: Visit `http://localhost:8000/docs`. The Swagger UI renders all 30+ endpoints.
- [ ] **Student Web App**: Visit `http://localhost:8000`. The Dashboard renders with summary cards and paper grid.
- [ ] **Curator Web App**: Visit `http://localhost:8000/curator`. The Curator Workbench loads with sidebar navigation.

---

## 2. Taxonomy & Reference Data Verification

- [ ] **Subtopics API**: Visit `http://localhost:8000/api/v1/subtopics?limit=5`.
  - Returns a JSON array with Crockford base32 ID format (`P[1-6]-[0-9A-Z]{6}`).
- [ ] **Total Syllabus Nodes**: Run `uv run caf taxonomy load`.
  - Expected: 6 Papers, 39 Chapters, 77 Topics, 264 Subtopics.
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

## 5. Security & Isolation Checks (Decision D2)

- [ ] **Decision D2 Compliance**:
  - Open Student App network tab in browser developer tools.
  - Verify that no requests to `/api/v1/curate/*` are made from the Student App.
  - Verify that no question text or answer text is sent to the Student frontend bundles.
- [ ] **Zero Shared UI Components**:
  - Student app and Curator tool are independently bundled with separate stylesheets and assets.

---

## 6. Clean Shutdown & Data Preservation

- [ ] **Stop Command**:
  - Press `Ctrl+C` in the terminal running `start.py` (or run `python stop.py`).
  - Terminal prints confirmation that PostgreSQL container is stopped.
- [ ] **Data Persistence**:
  - Restart the app: `python start.py`.
  - All previously entered study notes, progress marks, and mock test scores remain intact.
