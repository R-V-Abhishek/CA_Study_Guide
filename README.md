# CA Final Study Companion

An offline-first, single-user study operating system and exam-intelligence platform for CA Final aspirants.

---

## 🎯 What Is This?

Preparing for the CA Final examination requires mastering vast syllabus depths across all 6 papers. Standard study planners treat every chapter the same. The **CA Final Study Companion** connects the official ICAI syllabus hierarchy with **historical exam intelligence**:

- 🌲 **Canonical Syllabus Hierarchy**: Complete 4-tier tree (Paper → Chapter → Topic → Subtopic) across all 6 papers with 264 distinct subtopics.
- 🎯 **Historical Exam Intelligence**: Surfaces past exam questions, frequency metrics ($E$), marks weightage ($W$), and a 5-dot importance score (`●●●●○`) right at the subtopic you are studying.
- 📅 **Prioritized Weekly Study Plan**: Dynamic study schedule generator balancing high-weightage chapters and untouched topics based on your available weekly hours (15h to 35h).
- 🧠 **Anki-Style Spaced Revision Queue**: Automated interval-based active recall cards (`✓ Got it` / `≈ Shaky`) with confetti completion tracking.
- 📊 **Syllabus Coverage Audit**: Granular progress breakdown (Not Started, In Progress, Done) with 1-click CSV export.
- 📈 **Mock Test Tracker**: Log your test series scores and visualize your score progression with responsive charts.
- 📝 **Rich Markdown Notes**: Built-in distraction-free study notes editor with debounced auto-save.
- 🔒 **100% Private & Offline-First**: All your study progress, notes, and metrics remain locally on your computer in PostgreSQL. Zero cloud tracking.

---

## 👥 The Student-Curator Duality

As a CA Final aspirant, **you are also the subject-matter curator** of this tool. No generic software developer understands the nuances of Ind AS standards, SA standards, Transfer Pricing sections, or GST valuation rules better than you.

The tool provides automated text extraction and AI suggestions, but **you** make the final curation decisions. You will use the system in two phases:
1. **Phase 1: Content Curator Mode**: Ingest official ICAI papers, let the AI suggest syllabus mappings, and review them rapidly via keyboard in the Curator Workbench (`/curator`).
2. **Phase 2: Study Mode**: Use the curated intelligence daily in your personal Study App (`/`) to plan, revise, and track your syllabus completion.

---

## 💻 System Prerequisites

Before starting, make sure you have the following installed:

| Prerequisite | Minimum Version | Download Link | Notes |
|---|---|---|---|
| **Python** | 3.12+ | [python.org/downloads](https://www.python.org/downloads/) | **Windows users**: Check **"Add python.exe to PATH"** |
| **Docker Desktop** | Latest | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | Manages your local PostgreSQL database |
| **Google Gemini API Key** | Optional / Recommended | [Google AI Studio](https://aistudio.google.com/) | Powers the automated question classifier |

*Disk Space Required*: Approximately 3–5 GB for PostgreSQL storage, PDF blobs, and dependencies.

---

## ⚡ One-Time Setup (~10 Minutes)

1. **Clone or Download** this repository to your computer:
   ```bash
   git clone https://github.com/R-V-Abhishek/CA_Study_Guide.git
   cd CA_Study_Guide
   ```

2. **Ensure Docker Desktop is running** on your computer.

3. **Run the Setup Script**:
   - **Windows**: Double-click `setup.bat` (or open Command Prompt and run `python setup.py`).
   - **macOS / Linux**: Open Terminal and run:
     ```bash
     python3 setup.py
     ```
     *(or double-click `./setup.sh`)*

### What the Setup Script Does Automatically:
1. Verifies Python ≥ 3.12 and Docker engine status.
2. Creates your local `.env` configuration file and prompts for your `GEMINI_API_KEY`.
3. Starts the PostgreSQL container on port `5433` (isolated from any local Postgres).
4. Auto-installs `uv` (fast package manager) and all Python dependencies.
5. Applies database schema migrations and role permissions.
6. Loads the canonical 264-node CA Final syllabus taxonomy.

---

## 🚀 Daily Usage

Every day when you sit down to study:

### 1. Start the Companion
- **Windows**: Double-click `start.bat` (or run `python start.py`).
- **macOS / Linux**: Run `./start.sh` (or `python3 start.py`).

Your default web browser will automatically open:
- 📖 **Student Study App**: [http://localhost:8000](http://localhost:8000)
- 🛠️ **Curator Workbench**: [http://localhost:8000/curator](http://localhost:8000/curator)
- 📚 **Interactive API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Stop the Companion
When you finish your study session:
- Press `Ctrl + C` in the running terminal window.
- Or double-click `stop.bat` / run `python stop.py`.
- *Your PostgreSQL database stops cleanly and all your notes and study progress are preserved safely.*

---

## 🛠️ Phase 1: Content Curator Mode

*(Run this when loading new ICAI exam papers or suggested answers)*

The pipeline transforms raw ICAI Suggested Answers into structured study intelligence. Full details are in [docs/PIPELINE.md](docs/PIPELINE.md).

### Quick Pipeline Workflow:

```bash
# 1. Discover official PDF download links from ICAI website
uv run caf acquire discover

# 2. Download candidate PDFs into local blob store (batch of 10)
uv run caf acquire fetch --limit 10

# 3. View downloaded papers in catalogue
uv run caf acquire catalog

# 4. Extract Question & Answer pairs from confirmed PDFs
uv run caf extract run

# 5. Let AI classify questions to syllabus topics (requires GEMINI_API_KEY)
uv run caf classify run --limit 25
```

### Rapid Review in Curator Workbench (`/curator`):
Open **http://localhost:8000/curator** in your browser to access the **Review Queue**:
- **Side-by-Side View**: Official ICAI Question text on the left, model solution on the right.
- **AI Recommendation**: Primary suggestion badge with confidence score.
- **Fast Keyboard Shortcuts**:
  - `A` — **Accept** suggestion and publish to syllabus.
  - `E` — **Edit Node** (opens instant search across all 264 syllabus topics).
  - `N` — **None Fits** (out-of-syllabus or general question).
  - `X` — **Exclude** (instructions, front matter).
  - `→` / `L` — Next question.
  - `←` / `H` — Previous question.

### Recompute Exam Intelligence:
Once you have curated and accepted questions:
```bash
uv run caf intel compute
```
*This calculates marks weightage, appearance frequency, and generates your 5-dot topic importance scores.*

---

## 📖 Phase 2: Study Mode

Open **http://localhost:8000** to use your personal study interface:

### 1. Study Dashboard (`/`)
- Aggregate completion stats for Group 1 and Group 2.
- High-priority revision items due today.
- Direct links to your active chapters.

### 2. Papers & Syllabus Navigator (`/papers`)
- Browse all 6 canonical papers:
  - **P1**: Financial Reporting (FR)
  - **P2**: Advanced Financial Management (AFM)
  - **P3**: Advanced Auditing & Professional Ethics (Audit)
  - **P4**: Direct Tax Laws & International Taxation (DT)
  - **P5**: Indirect Tax Laws (IDT / GST)
  - **P6**: Integrated Business Solutions (IBS)
- Two-pane split explorer: Click any chapter on the left to inspect its topics, subtopics, exam marks weightage, and past question appearances on the right.
- Distraction-free **Markdown Notes Editor** with live preview and auto-save.

### 3. Weekly Study Plan (`/plan`)
- Choose your weekly budget (15, 20, 28, or 35 hours/week).
- Filter by Group 1, Group 2, or individual papers.
- Smart greedy scheduler generates daily study targets prioritizing high-weightage topics you have not covered yet.

### 4. Spaced Revision Queue (`/revision`)
- Active recall flashcard interface inspired by Anki.
- Displays syllabus context, overdue days, and personal study notes.
- Rate your recall: **✓ Got it** (advances interval) or **≈ Shaky** (resets interval).
- Smooth transitions and celebratory completion screen when you clear today's cards.

### 5. Syllabus Progress Audit (`/progress`)
- Complete checklist of all 264 subtopics with status pills (`○ Not Started`, `● In Progress`, `✓ Done`).
- Filter by status or weak coverage flags.
- **Export CSV**: Download a clean spreadsheet of your entire preparation progress.

### 6. Mock Test Tracker (`/mock`)
- Record test series attempts: Series name, Paper, Date, Score, and Max Marks.
- Interactive progression charts show your score trajectory against the 40% per-paper and 50% aggregate passing criteria.

---

## ⚙️ Personalizing Your Setup

### Change Your Target Exam Attempt
By default, the companion targets the `2026-05` (May 2026) attempt. To change this to November 2026:
1. Open `config/settings.toml` in any text editor.
2. Edit line 5:
   ```toml
   target_attempt_id = "2026-11"
   ```
3. Save the file. The companion will automatically calibrate its recency weights.

### Import Your Own Study Notes or Question Banks
If you have local coaching material, past papers, or personal question bank PDFs:
```bash
uv run caf acquire import /path/to/my_file.pdf
```

---

## 🔧 Troubleshooting

### "Database won't connect / Connection refused on port 5433"
- Ensure Docker Desktop is running before starting the app.
- Check container status:
  ```bash
  docker compose ps
  ```
- If the container is stopped, run `docker compose up -d`.

### "Port 8000 is already in use"
- You can run the app on an alternative port:
  ```bash
  uv run caf serve --port 8080
  ```
- Then open [http://localhost:8080](http://localhost:8080) in your browser.

### "I don't have a Google Gemini API Key"
- You can still use 100% of the Study App, manual note taking, syllabus navigation, and progress tracking without an API key!
- The API key is only used in Stage L3 for automated question classification suggestions. Without it, you can still categorize questions manually using the Curator Node Picker (`E` key).

For detailed platform-specific notes (Windows WSL2, Apple Silicon, Linux permissions), see [docs/PLATFORM_NOTES.md](docs/PLATFORM_NOTES.md).

---

## 🔍 Verification & Health Checks

To verify that all components are working correctly, consult the step-by-step checklist in [VERIFY.md](VERIFY.md).

You can also run the automated backend test suite at any time:
```bash
uv run pytest
```
*(All 61 tests verify contracts, database integrity, and Decision D2 leak prevention).*

---

## 📜 Architectural Decisions Reference

- **Decision D1**: Offline-first, single-user architecture.
- **Decision D2**: Strict separation — question/solution text is curator-only; student view contains only syllabus analytics and personal notes.
- **Decision D3**: Human-in-the-loop guarantee — no raw AI classification reaches the student view without human review.
- **Stable IDs**: Crockford base32 syntax (`P[1-6]-[0-9A-Z]{6}`) for permanent bookmarking across exam attempts.

---

*Happy Studying & All the Best for CA Final! 🎓*
