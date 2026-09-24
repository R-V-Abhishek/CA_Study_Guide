# CA Final Study Companion — Build Log & Project Journal

## 1. Project Overview & Vision
The **CA Final Study Companion** is an offline-first, single-user study operating system and exam-intelligence platform for CA Final aspirants. It provides:
1. **Canonical Syllabus Hierarchy**: Paper → Chapter → Topic → Subtopic with stable identifiers.
2. **Deterministic Study Tracking**: 3-state tracking (`not_started`, `in_progress`, `done`) with notes and timestamps.
3. **Historical Exam Intelligence**: Surfaces past exam questions, marks, and model answers inline at the exact subtopic being studied.
4. **Actionable Planning**: Intelligent prioritization based on historical weightage, recent attempt frequency, and weak coverage.

---

## 2. Core Architectural Principles
- **Separation of Planes**:
  - **Offline Plane (`caf` CLI)**: L0 (Taxonomy), L1 (Acquisition), L2 (Extraction), L3 (Classification), L4 (Curation/Publish), L5 (Intelligence).
  - **Live Plane (API & UI)**: L6 (FastAPI + React SPA). Reads only published core and intel data; zero LLM or scraping calls on the live path.
- **6 Postgres Schemas**:
  - `ref`: Canonical taxonomy, attempts, papers, doc types, anchors, weightages.
  - `ingest`: Staged discovery links, raw documents, parsed units, tag suggestions.
  - `core`: Published appearances, tags, and human curation decisions (irreplaceable).
  - `intel`: Derived intelligence scores and ingestion coverage.
  - `app`: User progress, settings, study sessions, and notes (irreplaceable).
  - `ops`: Pipeline runs, LLM token ledger, operational event logs.
- **Human-Confirmed Tags (Decision D3)**: No automated classification reaches the student view without human review.
- **Contract-Driven Design**: Rigid Pydantic interfaces (C0–C6) decouple each pipeline stage.

---

## 3. Milestone Roadmap

| Milestone | Scope | Status | Notes |
|---|---|---|---|
| **M0** | Foundations: Repo structure, uv workspace, Docker/Postgres, Alembic, contracts, common, DB models, `caf` CLI skeleton | 🟢 Complete | DB up on local Postgres 16; Alembic migrations apply/rollback verified; role grants applied; `caf status` active; C0–C6 contracts implemented. |
| **M1** | Taxonomy v1 + Usable Tracker: L0 registries, outline extractor, YAML loader, all 6 papers, L6 thin app | 🟢 Complete | Authored & verified syllabus trees for all 6 papers (39 chapters, 77 topics, 264 subtopics); weightages loaded; L6 API endpoints active; full automated test suite passing. |
| **M2** | Catalogue: L1 discovery (HTTP) for current scheme, catalogue review, downloader | 🟢 Complete | Deterministic inference, polite crawler, SHA-256 deduplicated fetcher, manual importer, catalogue review API/CLI. |
| **M3** | Extraction for one profile: L2 current-scheme Suggested Answers | 🟢 Complete | PyMuPDF block stream, deterministic segmenter, choice rules, V1–V7 validators, same-doc answer pairing, debug render HTML, manual overrides, C2 database persistence. |
| **M4** | Classification + Review: L0 descriptors + anchors, L3 cascade, L4 curation UI | 🟡 Up Next | L0 anchor index & descriptors, L3 hierarchical classification cascade, L4 curation UI & bulk accept. |
| **M5** | Intelligence v1: L5 E/F/W/I scores, weak flags, inline history | ⚪ Pending | |
| **M6** | Practice Signal + Planning: L2 RTP/MTP profiles, P signal, revision planner | ⚪ Pending | |
| **M7** | Depth Gate: 2017 & pre-2017 bands backfill gating | ⚪ Pending | |
| **M8** | Hardening: Backup verification, alarms, end-to-end tests | ⚪ Pending | |

---

## 4. Current Execution Log

### Session 1: Project Kickoff & Milestone 0 Foundations (Complete)
- **Documentation Analysis**: Reviewed `CA_Final_Study_Tool_System_Design.md`, `CA_Final_Technical_Implementation_Plan_v2.md`, and `CA_Final_Detailed_Implementation_Guide.md`.
- **System Architecture Initialized**:
  - `config/`: `settings.toml`, `sources.toml`, `models.toml`, `depth.toml`, `scoring.toml`.
  - `taxonomy/registry/`: `schemes.yaml`, `attempts.yaml`, `papers.yaml`, `doc_types.yaml`, `instruments.yaml`, `law_boundaries.yaml`.
  - `packages/`: `caf-contracts`, `caf-common`, `caf-db`, `caf-l0`, `caf-l1`, `caf-l2`, `caf-l3`, `caf-l4`, `caf-l5`, `caf-api`, `caf-cli`.
- **Milestone 0 Verification**:
  - PostgreSQL 16 on port 5432; Alembic migrations verified with clean apply/rollback cycle.
  - Idempotent role grants for `caf_pipeline`, `caf_curator`, `caf_app`.
  - Initialized independent git repository and pushed cleanly to remote.

### Session 2: Milestone 1 — Taxonomy v1 & Usable Tracker (Complete)
- **L0 Stable Node Identifiers**: Implemented Crockford base32 ID generation (`caf_l0/ids.py`) enforcing `P[1-6]-[0-9A-HJKMNP-TV-Z]{6}` syntax.
- **Syllabus Hierarchy Authored**:
  - Generated and structured complete syllabus trees in `taxonomy/papers/` for all 6 papers: P1 (FR), P2 (AFM), P3 (Audit), P4 (DT), P5 (IDT), P6 (IBS).
  - Authored official chapter-level weightage groupings in `taxonomy/weightage/` for P1–P6.
- **Enhanced Taxonomy Loader**:
  - Extended `TaxonomyLoader` to validate Crockford base32 format, strict level chaining (Paper → Chapter → Topic → Subtopic), seq uniqueness, and weightage midpoint range (90–110%).
  - Successfully loaded 39 chapters, 77 topics, and 264 subtopics into `ref.node` alongside `ref.weightage_section` and `ref.weightage_member` (Run ID: 3).
- **L6 Thin Study Tracker Backend (`caf_api`)**:
  - Implemented `GET /api/v1/papers`: lists papers with raw progress and chapter-weightage-weighted coverage.
  - Implemented `GET /api/v1/papers/{paper_id}/tree`: returns nested hierarchy with user progress status and personal notes.
  - Implemented `GET /api/v1/subtopics/{node_id}`: returns subtopic details with parent path, notes, status timestamps, chapter weightage, and past exam appearances.
  - Implemented `PUT /api/v1/subtopics/{node_id}/progress`: 3-state tracking (`not_started`, `in_progress`, `done`) with automatic transition event logging in `app.progress_event`.
  - Implemented `PUT /api/v1/subtopics/{node_id}/notes`: updates personal study notes in `app.note`.
  - Implemented `GET /api/v1/dashboard`: summarizes overall syllabus coverage %, Group 1 & Group 2 breakdown, and recent study activity feed.
- **Verification**: All 5 end-to-end API and business logic tests in `tests/test_milestone1.py` passing cleanly. Exit criterion met: The tool is immediately usable for daily study tracking across all 6 papers.

### Session 3: Milestone 2 — Acquisition & Catalogue (Complete)
- **Deterministic Metadata Inference (`caf_l1/infer.py`)**:
  - Implemented multi-factor deterministic metadata inference parsing URLs, breadcrumbs, link text, and filenames into canonical tuples (`attempt_id`, `paper_id`, `doc_type_id`, `series`).
  - Supports fuzzy matching against canonical paper titles via RapidFuzz, normalized regex delimiters, and auto-assignment of `catalog_status` (`inferred` vs `needs_curation`).
- **Crawler & Polite Rate Limiting (`caf_l1/robots.py`, `caf_l1/discover.py`)**:
  - Built `RobotsCache` parsing and honoring `robots.txt` per host with in-memory caching.
  - Implemented `RateLimiter` enforcing minimum interval delays (2.0s per host) to prevent server strain.
  - Built breadth-first crawler extracting PDF links from configured ICAI seed sources (`config/sources.toml`) into `ingest.discovery_link`.
- **Fetcher & Deduplication (`caf_l1/fetcher.py`)**:
  - Implemented polite downloader with PDF MIME validation and magic byte verification.
  - Implemented SHA-256 deduplication checking both DB records and content-addressed `BlobStore`.
- **Manual Import Pipeline (`caf_l1/importer.py`)**:
  - Created `ManualImporter` enabling bulk offline ingestion of local PDF files or directories directly into `BlobStore` and `ingest.document` with auto-inference.
- **Catalogue & Curator API (`caf_l1/catalog.py`, `caf_api/curate.py`)**:
  - Implemented curator review endpoints in `caf_api`: `GET /api/v1/curate/documents`, `POST /api/v1/curate/documents/{doc_id}/confirm`, `POST /api/v1/curate/documents/{doc_id}/reject`, and `PUT /api/v1/curate/documents/{doc_id}` for metadata overrides.
  - Added CLI commands under `caf acquire`: `discover`, `fetch`, `import`, `catalog`, and `confirm`.
- **Verification**:
  - Added automated test suite `tests/test_milestone2.py` verifying inference edge cases and end-to-end manual import + curation workflow.
  - Full test suite passing (7/7 tests). CLI catalogue inspection verified.

### Session 4: Milestone 3 — Extraction for Current-Scheme Suggested Answers (Complete)
- **Preflight & Text-Layer Verification (`caf_l2/preflight.py`)**:
  - Implemented character density inspection per page (>= 200 chars on >= 70% pages) to distinguish digital PDFs from scanned PDFs.
- **Positioned Block Stream & Normalization (`caf_l2/blocks.py`)**:
  - Built block extractor using PyMuPDF `get_text("dict", sort=True)`.
  - Implemented NFKC normalization, ligatures (`ﬁ` → `fi`), and PUA rupee symbols (`\uf0b9` → `₹`).
  - Implemented header/footer removal for repeating lines in top/bottom 8% with protection for content headings (`question`, `case scenario`, parts).
  - Emitted stable block IDs `p{page}-b{idx}`.
- **Profile Architecture (`profiles/s2023.suggested_answer.yaml`, `caf_l2/profiles.py`)**:
  - Formatted and compiled YAML extraction profile for `s2023.suggested_answer.v1` with regex anchors for questions, parts, subparts, marks, answers, OR alternatives, and choice rules.
  - Built fallback profile resolver `(scheme, doc_type, paper) -> (scheme, doc_type) -> (doc_type)`.
- **Deterministic Stateful Segmenter (`caf_l2/segmenter.py`)**:
  - Stateful state-machine parsing questions, parts, subparts, case stems, and MCQs.
  - Choice rule parsing from introductory pages (`Question 1 is compulsory, attempt any 4 of remaining 5`).
  - Marks rollup: non-gradable parent questions receive `marks = sum(children)` with `marks_source='summed'`, while leaves receive explicit marks.
  - Stable fingerprint generation: `sha1(doc_sha256 | label_path | normalized_text[:200])`.
- **Answer Pairing (`caf_l2/pairing.py`)**:
  - Paired answer text collected during interleaved parsing (`pairing_method='same_doc'`).
  - Supported MCQ answer key table parsing.
- **Deterministic Integrity Validators V1–V7 (`caf_l2/validators.py`)**:
  - Implemented V1 (contiguous numbering), V2 (gradable marks completeness), V3 (choice-aware attemptable marks check against paper_max), V4 (answer pairing completeness), V5 (length thresholds), V6 (MCQ options and keys), V7 (monotonic page spans).
  - Outcome resolution (`ok`, `ok_with_warnings`, `needs_review`) and per-unit parse confidence (`high`, `medium`, `low`).
- **Overrides & Debug Renderer (`caf_l2/overrides.py`, `caf_l2/render.py`)**:
  - Built manual override system (`overrides/<sha256>.yaml`) supporting patch and replace modes.
  - Implemented HTML debug renderer generating standalone color-coded line block tables with unit badges and validation flags.
- **Pipeline Orchestrator & CLI (`caf_l2/pipeline.py`, `caf_cli/extract.py`)**:
  - Orchestrated full pipeline: blob read → preflight → blocks → profile → segment → pair → override → validate → DB persistence (`ingest.unit` and `ingest.unit_answer`) with transaction safety.
  - Added CLI subcommands: `caf extract run`, `caf extract debug`, `caf extract report`.
- **Verification**:
  - Added comprehensive test suite `tests/test_milestone3.py` (6 tests).
  - Full project test suite passing (13/13 tests). All CLI commands verified.



