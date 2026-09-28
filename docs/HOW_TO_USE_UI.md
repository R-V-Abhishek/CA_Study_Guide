# CA Final Study Companion — UI User Guide

A step-by-step visual and operational guide for both applications:
1. **The Student Study App** (`http://localhost:8000`)
2. **The Curator Workbench** (`http://localhost:8000/curator`)

---

## 🎯 Quick Architecture & Role Context (For Developers)

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server (:8000)                  │
├──────────────────────────────┬──────────────────────────────┤
│      / (Root Path)           │      /curator (Subpath)      │
│   Student Study App (SPA)    │   Curator Workbench (SPA)    │
│  - Reads core & intel data   │  - Reviews question mappings │
│  - Private notes & progress  │  - Publishes to core schema  │
│  - Zero raw Q&A texts (D2)   │  - Full Question/Answer view │
└──────────────────────────────┴──────────────────────────────┘
```

- **Why Human Curation Exists**: The AI extraction pipeline pulls questions from official ICAI past papers, RTPs, and MTPs, and attempts to tag them to 1 of 264 syllabus subtopics. Even with multi-stage cascade models, AI precision is ~78.5%. A wrong tag means a student studies the wrong chapter or exam marks weightages are distorted. The Curator Workbench lets a human review questions with 1-key triage before they affect study metrics.

---

## 📖 Part 1: Student Study App (`http://localhost:8000`)

### 1. Dashboard (`/`)
When you launch the app, you arrive at the **Study Dashboard**:
- **Preparation Summary Cards**:
  - Overall Syllabus Progress (% completed, marked done, in-progress).
  - Group 1 vs. Group 2 completion meters (CA Final consists of Group 1: P1–P3, Group 2: P4–P6).
  - Next Due Revision countdown.
- **Papers Grid**: Quick-access cards for all 6 papers showing individual paper coverage bars.
- **Active Study Targets**: Top 3 high-weightage topics recommended for study today.

### 2. Papers & Syllabus Explorer (`/papers`)
- **Paper Grid View**: Click any of the 6 papers (e.g., *Paper 1: Financial Reporting*).
- **Two-Pane Explorer**:
  - **Left Sidebar**: Canonical syllabus hierarchy (Chapter → Topic → Subtopic).
    - Status pills next to each topic: `○ Not Started`, `● In Progress`, `✓ Done`.
    - Clicking a subtopic selects it and loads the right pane.
  - **Right Detail Pane**:
    - **Header**: Paper code, chapter title, and stable Crockford Base32 ID (e.g., `P1-BXTF71`).
    - **Historical Intelligence**:
      - 5-dot Importance Rating (`●●●●○`).
      - Historical exam frequency and total marks appeared.
      - Inline past appearances list: Attempt (e.g., May 2024), Question Number (Q1(a)), and Marks (10 Marks).
    - **Progress Toggle**: Dropdown or buttons to change state (`Not Started` → `In Progress` → `Done`).
    - **Distraction-Free Notes Editor**:
      - Rich Markdown formatting toolbar (Bold, Italic, Headings, Bullet Lists, Code blocks).
      - **Edit** vs. **Preview** tab toggle.
      - 2-second debounced auto-save with live status indicator (`Unsaved changes` → `Saving...` → `Auto-saved`).

### 3. Weekly Study Plan (`/plan`)
A dynamic greedy scheduler that balances high-weightage chapters with untouched topics:
- **Top Controls**:
  - **Weekly Budget Dropdown**: Select `15h`, `20h`, `28h`, or `35h` per week.
  - **Filter**: All Papers, Group 1 Only, Group 2 Only, or a specific paper.
  - **Regenerate Button (↺)**: Re-runs the greedy allocation algorithm based on fresh syllabus status.
- **Timeline View**:
  - Grouped into day-by-day task buckets (**Today**, **Day 2**, **Day 3**, etc.).
  - Each item displays:
    - Priority number badge (①, ②, ③).
    - Allocated study time (e.g., `2h 30m`).
    - Paper badge (e.g., `P1 FR`).
    - Factual reason string (e.g., *"High exam weightage (14% of paper) and currently untouched"*).
    - **Start / Continue Button**: One click jumps directly to that subtopic in the Papers view.
    - Completed tasks appear with strikethrough styling and muted color.

### 4. Spaced Revision Queue (`/revision`)
An active recall flashcard interface inspired by SuperMemo/Anki algorithms:
- **Single-Card Recall Mode**:
  - Shows syllabus path, chapter title, and subtopic name.
  - Overdue indicator (e.g., *"Due today"*, *"Overdue by 2 days"*).
  - Expandable **Personal Notes Preview** to test recall before peeking.
- **Recall Evaluation Buttons**:
  - **✓ Got it** (Green): Advances the repetition interval (Stage 1: 1 day → Stage 2: 3 days → Stage 3: 7 days → Stage 4: 21 days), triggers confetti burst, and smoothly animates to the next card.
  - **≈ Shaky — reset** (Amber): Resets the repetition interval back to Stage 1.
- **Completion Screen**: Once the queue is empty, displays a celebratory *"All caught up for today! 🎉"* screen and preview of upcoming revisions for the next 7 days.

### 5. Syllabus Progress Audit (`/progress`)
- Complete checklist of all 264 subtopics across all 6 papers.
- **Filters**: Filter by Status (`All`, `Not Started`, `In Progress`, `Done`) and Weak Flags.
- **Export CSV Button**: In the top-right corner, click **Export CSV** to download `ca_final_syllabus_progress.csv` for offline review in Excel or Google Sheets.

### 6. Mock Test Tracker (`/mock`)
- **Score Progression Chart**: Interactive line chart powered by Recharts plotting your mock test scores chronologically.
  - 40% Individual Paper Passing line.
  - 50% Aggregate Passing line.
- **Log New Test**: Click **+ Log Mock Test Result**:
  - Modal prompts for: Paper, Test Series Name (e.g., ICAI MTP Series 1), Score obtained, Max Marks, Date, and Key Learnings / Mistakes.
  - Saves instantly to `app.mock_test` and updates the chart.

---

## 🛠️ Part 2: Curator Workbench (`http://localhost:8000/curator`)

Access this interface to review questions extracted from official ICAI Suggested Answers, RTPs, and MTPs.

### 1. Keyboard-Driven Review Queue (`/curator/queue`)
Designed for high-speed triage without touching the mouse:

```
┌──────────────────────────────────────────────┬───────────────────────────────┐
│              LEFT PANE (8 Cols)              │      RIGHT PANE (4 Cols)      │
│  - Unit #ID, Paper, Attempt, Marks           │  - Primary Suggestion Tag     │
│  - Official ICAI Question Text               │  - Confidence Bucket (A/B/C)  │
│  - Official ICAI Model Solution              │  - Secondary Alternative Tags │
└──────────────────────────────────────────────┴───────────────────────────────┘
```

#### Keyboard Shortcuts:
| Key | Action | What It Does |
|---|---|---|
| `A` | **Accept** | Confirms primary suggestion and publishes question to syllabus. |
| `E` | **Edit Node** | Opens 264-node Search Modal to pick the correct syllabus subtopic. |
| `N` | **None Fits** | Marks unit as general or out of current syllabus scheme. |
| `X` | **Exclude** | Excludes front-matter, instructions, or non-academic text. |
| `→` or `L` | **Next** | Advances to next question without deciding. |
| `←` or `H` | **Previous** | Returns to previous question. |

### 2. Node Picker Modal (`E` Key)
- Pressing `E` anywhere in the Review Queue pops up the **Node Picker Modal**.
- Instant full-text search across all 264 syllabus topics by chapter, title, standard name (e.g., *"Ind AS 116"* or *"Transfer Pricing"*), or Crockford ID (`P1-BXTF71`).
- Press `Enter` to confirm the selected node, or `Escape` to cancel.

### 3. Bulk Accept Bucket A (`/curator/bulk`)
- Shows a list of ingested documents where the AI cascade achieved high-confidence consensus (Bucket A $\ge 85\%$).
- Displays the count of high-confidence questions ready for instant publishing.
- Click **Bulk Accept All** to publish all Bucket A units in that document in one transaction.

### 4. Document Catalogue (`/curator/documents`)
- Displays all ingested PDF documents in the system.
- Shows:
  - Document Title.
  - Exam Attempt (e.g., `2024-05`).
  - Paper (`P1` to `P6`).
  - Document Type (`suggested_answer`, `rtp`, `mtp`).
  - Ingestion Status (`inferred`, `confirmed`, `rejected`).
  - SHA-256 deduplication hash and page count.

### 5. Taxonomy Explorer (`/curator/taxonomy`)
- Complete reference explorer for the canonical syllabus hierarchy.
- Click any node to copy its canonical Crockford Base32 ID to clipboard.

### 6. System Health & Alarms (`/curator/system`)
- **Operational Alarms**: Monitors all 5 system health checks:
  - **A1: Unclassified Spike**: Warns if unclassified units exceed threshold.
  - **A2: Pipeline Failure**: Alerts if any ingestion or extraction run failed.
  - **A3: Stale Scores**: Alerts if intelligence scores have not been recomputed after new decisions.
  - **A4: Depth Gate Drift**: Alerts if historical syllabus mapping drifts.
  - **A5: Unverified Document Alert**: Flags downloaded documents pending metadata confirmation.
- **Recompute Scores Button**: Click **Recompute Intelligence Scores** to run the L5 engine on demand (`POST /api/v1/curate/intel/recompute`).
- **Backup History**: Lists automated PostgreSQL `.dump` backups and timestamps.

---

## 💡 Practical Workflow Example

1. **Step 1**: Ingest a new Suggested Answer PDF via CLI:
   ```bash
   uv run caf acquire import /path/to/P1_SuggestedAnswers_May2024.pdf
   uv run caf extract run
   uv run caf classify run --limit 20
   ```
2. **Step 2**: Open `http://localhost:8000/curator`.
3. **Step 3**: Press `A` to accept high-confidence questions, or `E` to adjust any question tagged to the wrong standard.
4. **Step 4**: Go to `/curator/system` and click **Recompute Intelligence Scores**.
5. **Step 5**: Open `http://localhost:8000` — the newly published questions and updated marks weightages now appear in your Study Plan and Papers view!
