# CA Final Study Companion — Data Pipeline Guide

This guide walks you through the data pipeline from official ICAI PDFs to study intelligence. 

> **Duality Note**: As a student preparing for CA Final, you are also the subject matter curator of this tool. No external developer knows the CA Final syllabus nuance (Ind AS standards, SA standards, direct tax sections, GST provisions) better than you. The pipeline does the heavy lifting with automated text extraction and AI suggestions, but you make the final curation calls before questions become part of your revision plan.

---

## Pipeline Overview

```
L1: Acquire      Official ICAI PDFs discovered, downloaded, and deduplicated
       │
L2: Extract      Questions & answers segmented into discrete study units
       │
L3: Classify     AI cascade tags units to syllabus nodes (Bucket A/B/C/D)
       │
L4: Curate       You review suggestions in the Curator Workbench (Keyboard-driven)
       │
L5: Intelligence Historical weightage (W), exam frequency (E), and revision signals computed
       │
L6: Study        Surfaced in your Study App (Dashboard, Syllabus, Plan, Revision)
```

---

## Prerequisites

Before running pipeline commands:
1. Complete `python setup.py` once.
2. Ensure the database is running: `docker compose up -d` (or `python start.py`).
3. Set your `GEMINI_API_KEY` in `.env` if you want AI-assisted classification (L3).

All commands below are run using `uv run caf <command>`.

---

## Stage L1: Acquisition (Official PDFs)

Official sources are configured in `config/sources.toml` (Suggested Answers, RTPs, MTPs, Case Scenario Booklets).

### 1. Discover Official PDF Links
Crawl configured ICAI web pages to find downloadable PDFs:
```bash
uv run caf acquire discover
```
*Expected output*: `Discovered N link(s) across configured sources.`

### 2. Fetch / Download PDFs
Download discovered candidate PDFs into the local blob store (`data/blobs/`). Downloads are rate-limited and politeness-managed:
```bash
# Download up to 10 PDFs
uv run caf acquire fetch --limit 10
```
*Expected output*: `Fetch run complete. Downloaded 10 document(s).`

### 3. Review the Ingested Catalogue
Inspect downloaded documents and their inferred metadata (Paper, Exam Attempt, Document Type):
```bash
uv run caf acquire catalog --status inferred
```

### 4. Confirm Document Metadata
Confirm a document once you verify its attempt and paper ID:
```bash
uv run caf acquire confirm <DOC_ID>
```

### (Alternative) Manual PDF Import
If you have downloaded ICAI PDFs manually, import them directly:
```bash
# Import a single PDF file
uv run caf acquire import /path/to/Suggested_Answers_May2024_Paper1.pdf

# Or import an entire folder of PDFs
uv run caf acquire import /path/to/my_icai_pdfs/
```

---

## Stage L2: Extraction (Q&A Units)

Extracts structured question-and-answer units from confirmed PDF files using layout-aware font and coordinate segmentation.

### 1. Run Unit Extraction
```bash
# Extract units from all pending confirmed documents
uv run caf extract run

# Or extract from a specific document ID
uv run caf extract run --doc-id <DOC_ID>
```
*Expected output*: `Extracted 14 units across 1 document(s). Validated against V1–V7 checks.`

### 2. Inspect Extraction Quality
```bash
uv run caf extract stats
```

---

## Stage L3: Classification (AI Suggestions)

Matches each extracted question to the canonical 264 syllabus topics using a 3-run AI cascade with deterministic keyword anchors.

> **Requires**: Valid `GEMINI_API_KEY` in `.env`.

### 1. Run Classification
```bash
# Classify up to 25 pending units
uv run caf classify run --limit 25

# Filter by a specific paper (e.g., P1 for Financial Reporting)
uv run caf classify run --paper P1 --limit 20
```

Units are sorted into confidence buckets:
- **Bucket A (High Confidence ≥ 85%)**: Clear consensus across cascade runs.
- **Bucket B (Medium Confidence 65–84%)**: Good candidate, recommended for quick review.
- **Bucket C (Low Confidence < 65%)**: Ambiguous question; requires curator review.
- **Bucket D (Multi-topic)**: Comprehensive case study spanning multiple subtopics.

---

## Stage L4: Human Curation (Curator Workbench)

Per System Design Decision D3: **No automated classification reaches your study view without your review.**

You review and approve questions through the high-speed web interface:

1. Start the app if not running:
   ```bash
   python start.py
   ```
2. Navigate to the Curator Workbench:
   **http://localhost:8000/curator**
3. Use the **Review Queue**:
   - Question text and official solution are displayed side-by-side.
   - Recommended syllabus tags are highlighted with confidence scores.
   - **Keyboard Shortcuts**:
     - `A` — **Accept** recommended topic tag.
     - `E` — **Edit Node** (opens fast modal search across all 264 syllabus topics).
     - `N` — **None Fits** (out of syllabus or general question).
     - `X` — **Exclude** (non-academic front matter).
     - `L` or `→` — Next unit.
     - `H` or `←` — Previous unit.

### Bulk Accept for Bucket A
If you trust the high-confidence consensus for a document, use the **Bulk Accept** page (`/curator/bulk`) to approve all Bucket A units in one click.

---

## Stage L5: Exam Intelligence Computation

Once questions are curated and published, compute the derived intelligence scores:

```bash
uv run caf intel compute
```

This calculates:
1. **Exam Weightage Score ($W$)**: Historical marks distribution across exam attempts.
2. **Frequency Score ($E$)**: Recency and cadence of appearances.
3. **Practice Signal ($P$)**: Depth of coverage in RTPs and MTPs.
4. **Overall Importance Rating ($I$)**: The 1-to-5 dot rating (`●●●●●`) shown on every subtopic.
5. **Weak Coverage Flags ($\blacktriangleright$)**: Highlights high-weightage topics you haven't revised recently.

---

## Stage L6: Study Time!

All intelligence is now live in your personal study app:
- Open **http://localhost:8000**
- View your personalized **Weekly Plan** (`/plan`)
- Clear your **Spaced Revision Queue** (`/revision`)
- Check syllabus coverage on **Progress Audit** (`/progress`)
