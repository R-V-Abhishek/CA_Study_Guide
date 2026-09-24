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
| **M1** | Taxonomy v1 + Usable Tracker: L0 registries, outline extractor, YAML loader, all 6 papers, L6 thin app | 🟡 In Progress | Registries authored & verified (`schemes`, `attempts`, `papers`, `doc_types`, `instruments`, `law_boundaries`); initial ref data loaded. Authoring P1–P6 syllabus trees next. |
| **M2** | Catalogue: L1 discovery (HTTP) for current scheme, catalogue review, downloader | ⚪ Pending | |
| **M3** | Extraction for one profile: L2 current-scheme Suggested Answers | ⚪ Pending | |
| **M4** | Classification + Review: L0 descriptors + anchors, L3 cascade, L4 curation UI | ⚪ Pending | |
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
  - `packages/`:
    - `contracts`: Pure Pydantic models for C0 through C6 contracts.
    - `common`: Typed settings loader, structured logging, `BlobStore`, `open_run` context.
    - `db`: SQLAlchemy 2.0 ORM models for all 6 Postgres schemas (`ops`, `ref`, `ingest`, `core`, `intel`, `app`), Alembic migration `0001_initial_schema`, idempotent role grants.
    - `l0_taxonomy`: `TaxonomyLoader` with dry-run planning and schema application.
    - `cli`: `caf` CLI with `status`, `db (ping, migrate, rollback, grants)`, `taxonomy load`.
- **Milestone 0 Verification**:
  - Installed and configured local PostgreSQL 16 on port 5432.
  - Executed and validated Alembic migration `0001_initial_schema` (apply & rollback both verified).
  - Applied schema and role grants (`caf_pipeline`, `caf_curator`, `caf_app`).
  - Ran `caf status` showing healthy DB connection and operational logging.
  - Successfully loaded all initial reference registries into `ref.*` tables via `caf taxonomy load --apply` (Run ID: 2).

