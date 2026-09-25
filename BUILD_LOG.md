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
| **M4** | Classification + Review: L0 descriptors + anchors, L3 cascade, L4 curation UI | 🟢 Complete | L0 anchor registry (93 anchors), 27 chapter descriptors, deterministic anchor extractor, 3-run consistency cascade, A/B/C/D bucketing, L4 curation API, bulk accept, atomic publishing. |
| **M5** | Intelligence v1: L5 E/F/W/I scores, weak flags, inline history | 🟡 Up Next | E/F/W/I score engine, weak flags, inline exam appearances on subtopic tracker, coverage indicators. |
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

### Session 5: Milestone 4 — Classification & Curation Review (Complete)
- **L0 Anchor Registry & Syllabus Descriptors (`taxonomy/registry/anchors.yaml`, `taxonomy/descriptors/descriptors.yaml`)**:
  - Authored 93 anchor definitions mapping Indian Accounting Standards (`IndAS`), Auditing Standards (`SA`, `SQC`, `SQM`), Direct Tax sections (`ITA1961`), and Indirect Tax sections (`CGST`, `IGST`, `CUSTOMS`) to canonical syllabus nodes.
  - Authored 27 chapter descriptors and domain keyword sets across papers P1, P3, P4, P5.
  - Enhanced `TaxonomyLoader` (`caf_l0/loader.py`) to validate and load anchors into `ref.anchor` and descriptors into `ref.descriptor` (Taxonomy Version 4).
- **Deterministic Anchor Extractor & Lookup (`caf_l3/anchors.py`)**:
  - Implemented regex extractors for Ind AS, SA, SQC/SQM, Income-tax sections, and GST/Customs sections with contextual Act disambiguation (IGST vs Customs vs CGST).
  - Implemented `lookup_anchor_candidates` aggregating weights from `ref.anchor`.
- **Classification Cascade & Consistency Protocol (`caf_l3/cascade.py`)**:
  - Implemented 2-step hierarchy: Step 1 (Chapter selection) and Step 2 (Subtopic selection).
  - Implemented multi-run consistency protocol: R1 (standard order) vs R2 (shuffled order seeded by unit fingerprint), with R3 tie-break.
  - Evidence-based bucket assignment: Bucket A (Consensus + Anchor Consistent), Bucket B (Consensus + Anchor Conflicting), Bucket C (Tie-break resolved), Bucket D (No consensus / gap).
  - Implemented concise gist generator (≤25 words concept summary).
- **L3 Pipeline Orchestrator & CLI (`caf_l3/pipeline.py`, `caf_cli/classify.py`)**:
  - Automated selection of gradable pending units, classification, and persistence to `ingest.tag_suggestion` (primary and secondary roles).
  - Added CLI commands: `caf classify run`, `caf classify report`.
- **L4 Curation, Decisions & Publishing (`caf_l4/publish.py`, `caf_api/curate.py`, `caf_cli/curate.py`)**:
  - Built atomic publishing engine: records `core.decision`, upserts `core.appearance` with normalized tag shares (primary=1.0, secondary=0.5), computes `law_stale` against `ref.law_boundary`, marks units as decided, and logs audit events to `core.change_log`.
  - Implemented `bulk_accept_bucket_a` for fast, human-confirmed document sign-off.
  - Added FastAPI curation endpoints: `GET /api/v1/curate/queue`, `POST /api/v1/curate/units/{unit_id}/decision`, `POST /api/v1/curate/documents/{doc_id}/bulk_accept_bucket_a`.
  - Added CLI commands: `caf curate queue`, `caf curate bulk-accept`, `caf curate stats`.
- **Verification**:
  - Added automated test suite `tests/test_milestone4.py` (6 tests).
  - Full project test suite passing (19/19 tests across M1–M4).

### Session 6: Milestone 5 — Intelligence Engine v1 (Complete)
- **Scoring Configuration (`config/scoring.toml`, `caf_l5/config.py`)**:
  - Implemented typed `ScoringConfig` loader with deterministic 16-character SHA-256 hash.
  - Configured parameters: $H_{exam} = 24$ months, $H_{practice} = 12$ months, $\kappa = 0.5$ (P6 cross-paper), $\lambda = 0.5$ (law-stale), $N = 5$ attempts, `weak_flag_min_hits = 3`, weights $\{exam: 0.6, practice: 0.2, prior: 0.2\}$.
- **Core Intelligence Engine & Decay (`caf_l5/scoring.py`)**:
  - Whole-month attempt distance calculation relative to target attempt $T$: $age(a) = (T.year - a.year) \times 12 + (T.month - a.month)$ (ignores appearances with $age < 0$).
  - Exponential decay computation: $2^{-age / H}$.
  - Attributed marks: $m(a,s) = marks(a) \cdot share(a,s) \cdot \kappa(a,s) \cdot \lambda(a)$.
  - Hierarchy-aware tag attribution supporting subtopic-level, topic-level, and chapter-level tags.
  - Weightage prior: $W(s) = section\_marks(\sigma) / |applicable\_subtopics\_in\_\sigma|$.
  - Paper-level normalization and composite Importance Score: $I(s) = 0.6 \hat{E}(s) + 0.2 \hat{P}(s) + 0.2 \hat{W}(s)$.
  - Ingestion coverage tracking across papers and attempts (`intel.ingestion_coverage`).
  - Atomic score run swapping in `intel.score_run` with retention of last 10 runs.
- **Explainability & "Why" Payload (`caf_l5/why.py`)**:
  - Implemented `get_subtopic_why` returning full mathematical transparency: every contributing appearance with raw marks, share, $\kappa$, $\lambda$, attributed marks, age, decay factor, and weighted contribution; weightage section priors; normalization maxima; and frequency window hits.
- **Weak-Coverage Flags & Weighted Coverage (`caf_l5/service.py`)**:
  - Evaluated weak flag rule: $weak(s) = applicable(s, T) \land F(s) \ge 3 \land freq\_window \ge 5 \land status(s) = 'not\_started'$.
  - Thin data guard ($freq\_window \ge N$) preventing premature alerts on incomplete exam history.
  - Implemented weighted syllabus coverage: $cov(paper) = \sum_{s \text{ done, app}} W(s) / \sum_{s \text{ app}} W(s)$ with group and overall aggregations.
- **Serving & Student API Integrations (`caf_api/routes.py`, `caf_api/curate.py`)**:
  - Enhanced `GET /api/v1/tree` and `GET /api/v1/papers/{id}/tree` with `importance`, `freq_hits`, `freq_window`, `weak`, and `applicable` fields.
  - Enhanced `GET /api/v1/subtopics/{id}` with complete `score` object and inline historical exam appearances (`core.appearance`).
  - Added `GET /api/v1/meta`: versions, target attempt, last computation timestamp, ingestion coverage indicator.
  - Enhanced `GET /api/v1/dashboard`: weighted syllabus coverage, top weak subtopics, and ingestion coverage indicator.
  - Added `GET /api/v1/why/subtopic/{node_id}` for on-demand score explainability.
  - Added curator trigger `POST /api/v1/curate/intel/recompute`.
- **CLI Commands (`caf_cli/intel.py`, `caf_cli/main.py`)**:
  - `caf intel recompute [--target-attempt YYYY-MM] [--shadow]`
  - `caf intel report [--paper Px] [--top N]`
  - `caf intel why <node_id>`
  - `caf intel coverage`
- **Verification**:
  - Added automated test suite `tests/test_milestone5.py` (6 tests).
  - All 25 project tests passing (`uv run pytest` -> 25/25 passed). All CLI commands verified.

### Session 7: Milestone 6 — Practice Signal + Planning (Complete)
- **Practice L2 Extraction Profiles & Cross-Doc Pairing (`profiles/`, `caf_l2/pairing.py`)**:
  - Authored YAML extraction profile for Revision Test Papers: `profiles/s2023.rtp.yaml` (`doc_type: rtp`).
  - Authored YAML extraction profile for Mock Test Papers answers: `profiles/s2023.mtp_answer.yaml` (`doc_type: mtp_answer`).
  - Authored YAML extraction profile for Case Scenarios: `profiles/s2023.case_scenarios.yaml` (`doc_type: case_scenarios`).
  - Implemented `pair_cross_doc_answers` in `caf_l2/pairing.py` to match question units with answer units across distinct documents by `label_path` (`pairing_method='cross_doc'`).
- **Practice Signal Scoring ($P(s)$)**:
  - Verified exponential decay with half-life $H_{practice} = 12$ months.
  - Verified integration with composite importance score $I(s) = 0.6 \hat{E} + 0.2 \hat{P} + 0.2 \hat{W}$.
- **Next-Week Study Planning Engine (`caf_l5/planning.py`)**:
  - Implemented effort budget allocation: $budget\_items = \lfloor (hours\_per\_week \times 60) / minutes\_per\_subtopic \rfloor$.
  - Priority scoring: $score(s) = I(s) + 0.25 \cdot [weak(s)] + 0.10 \cdot [status = in\_progress]$.
  - Implemented greedy allocation respecting per-chapter diversity caps ($\le 3$ picks per chapter).
  - Implemented factual reason generator: `"Asked in {F} of last {freq_window} exams ({exam_marks_total} marks); weightage section {σ}: {min}-{max}%"`.
  - Added optional scoping by `paper_id` and `group_no`.
- **Spaced-Repetition Revision Queue (`caf_l5/revision.py`)**:
  - Implemented dynamic scheduling across review intervals: `[3, 7, 21, 60]` days.
  - Handled shaky outcomes resetting stage $k$ to 0.
  - Ordered overdue subtopics by $I(s)$ descending, then overdue days descending.
  - Implemented `record_revision_outcome` updating `app.revision_event` and `app.progress.last_revised_at`.
- **API Endpoints (`caf_api/routes.py`)**:
  - `GET /api/v1/plan`: next-week plan with factual reasons and candidate scoring.
  - `GET /api/v1/revision/due`: spaced-repetition due list.
  - `POST /api/v1/subtopics/{id}/revisions`: record revision outcomes (`ok` or `shaky`).
  - `GET /api/v1/mock-tests`, `POST /api/v1/mock-tests`, `DELETE /api/v1/mock-tests/{id}`: mock test tracker CRUD.
  - `GET /api/v1/dashboard`: updated to include `plan_preview` (top 5 picks) and `revision_due_count`.
- **CLI Commands (`caf_cli/plan.py`, `caf_cli/revision.py`, `caf_cli/mock_test.py`, `caf_cli/main.py`)**:
  - `caf plan [--paper Px] [--group N] [--hours N]`
  - `caf revision list [--paper Px]`, `caf revision log <node_id> [--outcome ok|shaky]`
  - `caf mock-test list [--paper Px]`, `caf mock-test log --paper Px --score N [--max-score N] [--date YYYY-MM-DD]`, `caf mock-test delete <id>`
- **Verification**:
  - Added automated test suite `tests/test_milestone6.py` (6 tests).
  - Full project test suite passing (31/31 tests across M1–M6). All CLI commands verified.

### Session 8: Milestone 7 — Depth Gate Tooling (Complete)
- **Shadow Scoring Recomputation (`caf_l5/scoring.py`)**:
  - Extended `recompute_scores` with `provisional_items: list[tuple[Appearance, AppearanceTag]]` for shadow scoring runs.
  - Updated `published_coverage`, `paper_windows`, and `apps_with_tags` to incorporate provisional appearances and tags.
  - Protected ScoreRuns referenced by `intel.depth_gate_report` during automated retention cleanup (`keep last 10 runs`).
- **Depth Gate Engine (`caf_l5/depth_gate.py`)**:
  - Pure-Python Spearman rank correlation `compute_spearman_correlation(x, y)` with fractional rank tie-handling `compute_ranks(values)`.
  - TOML configuration loader `load_depth_config(config_path="config/depth.toml")`.
  - Implemented `compute_depth_gate(session, paper, band, top_k=50, record_report=True)`:
    - Resolved target current paper.
    - Acquired or computed baseline current score run.
    - Gathered band gradable units and deduplicated primary bucket A/B shadow tag suggestions.
    - Constructed provisional `Appearance` and `AppearanceTag` items with attribution and law staleness checks.
    - Computed shadow score run with provisional appearances.
    - Evaluated top-$K$ sets for baseline and shadow ($K = \min(50, N)$).
    - Calculated Jaccard similarity: $|top\_K(base) \cap top\_K(shadow)| / |top\_K(base) \cup top\_K(shadow)|$.
    - Calculated Spearman rank correlation over the union of top-$K$ sets.
    - Detected `newly_asked_nodes`: subtopics with 0 exam appearances in baseline and $>0$ in shadow.
    - Computed `units_to_review` and `est_review_hours` using median `seconds_spent` over historical curator decisions (defaulting to 45.0s when $<5$ decisions).
    - Evaluated recommendation: `continue` if $jaccard < 0.9$ or $new\_nodes \ge 10$; else `continue_practice_value` if paper has `practice_value = true` in `config/depth.toml`; else `stop`.
    - Persisted report to `intel.depth_gate_report`.
  - Historical query service `get_depth_gate_reports(session, paper, band)`.
- **CLI Commands (`caf_cli/depth.py`, `caf_cli/main.py`)**:
  - `caf depth gate --paper Px --band B [--top-k 50]`: runs depth gate computation and displays full comparison metrics table.
  - `caf depth report [--paper Px] [--band B]`: lists historical depth gate reports in Rich table.
- **Verification**:
  - Added automated test suite `tests/test_milestone7.py` (6 tests covering ranking, TOML loading, shadow scoring with provisional items, workflow execution, CLI commands, and decision branching).
  - Full project test suite passing (37/37 tests across M1–M7). All CLI commands verified.

### Session 9: Milestone 8 — Hardening (Complete)
- **Backup, Restore & Verification Engine (`caf_common/backup.py`)**:
  - Implemented `create_backup` performing custom-format `pg_dump -Fc`, blob directory synchronization (`data/blobs/`), configuration archiving (`taxonomy/`, `config/`, `overrides/`, `profiles/`), retention rotation, and `ops.event` recording (`code=BACKUP_OK`).
  - Implemented `verify_backup` executing monthly restore drill into scratch database (`caf_verify`), verifying exact row counts for 10 critical tables across `app.*` and `core.*`, and logging `ops.event` (`code=BACKUP_VERIFIED_OK`).
  - Implemented `rotate_backups` enforcing retention policy: 14 daily and 8 weekly dumps preserved, older stale dumps pruned.
  - Implemented `list_backups` returning existing backup dumps with sizes, ages, and timestamps.
- **System Observability & Alarms Engine (`caf_common/alarms.py`)**:
  - Implemented `evaluate_system_alarms` monitoring 5 operational conditions per Plan §6.6 / Guide §6.6:
    - `BACKUP_STALE`: backup older than 48 hours or absent.
    - `ZERO_LINKS_DISCOVERED`: latest seed discovery returned 0 links.
    - `EXTRACTION_FAILURE_HIGH`: extraction failure rate > 20% in latest run.
    - `BUDGET_CAP_REACHED`: run aborted due to budget cap.
    - `BUCKET_A_PRECISION_DROP`: human acceptance precision on Bucket A suggestions < 80%.
  - Integrated into `caf status` CLI command and `GET /api/v1/system/health` API endpoint.
- **Model Re-evaluation Procedure (`caf_l3/evaluate.py`, `caf classify evaluate`)**:
  - Implemented `evaluate_model_on_reviewed_decisions` assessing classifier proposals against human curator decisions in `core.decision`.
  - Computed sample totals, matches, Top-1 agreement, and precision for each confidence bucket (A, B, C, D).
  - Quality gating: enforces Bucket A precision $\ge 80\%$ (or configurable threshold) prior to switching models.
- **CLI Commands (`caf_cli/backup.py`, `caf_cli/classify.py`, `caf_cli/main.py`)**:
  - `caf backup run [--backup-dir DIR] [--target-dir DIR]`
  - `caf backup verify [--dump-file FILE] [--scratch-db NAME]`
  - `caf backup list [--backup-dir DIR]`
  - `caf classify evaluate [--threshold 0.80] [--min-samples 5]`
  - Enhanced `caf status` with live System Health & Alarms table.
- **API Endpoints (`caf_api/routes.py`)**:
  - `GET /api/v1/system/health`: returns overall system status and active alarms.
  - `GET /api/v1/system/backups`: returns list of backups with sizes and ages.
  - `POST /api/v1/system/backups`: triggers immediate backup creation.
  - `GET /api/v1/system/model-evaluation`: returns model evaluation report against reviewed decisions.
- **Verification**:
  - Added automated test suite `tests/test_milestone8.py` (7 tests covering rotation, creation, live verification drill, alarms, model evaluation, API endpoints, and CLI commands).
  - Full project test suite passing (44/44 tests across M1–M8). All CLI commands verified.


