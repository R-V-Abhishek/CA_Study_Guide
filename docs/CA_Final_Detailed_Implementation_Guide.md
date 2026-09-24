# Detailed Implementation Guide
## CA Final Study Companion — Execution Manual for Layers L0–L6

| | |
|---|---|
| **Document type** | Detailed Implementation Guide (v1.0) |
| **Parent document** | `CA_Final_Technical_Implementation_Plan_v2.md` — the Plan defines *what* and the contracts; this Guide defines *how* |
| **Rule** | If this Guide contradicts the Plan, the Plan wins and this Guide gets fixed. Anything here may change without an architecture review **as long as** contracts C0–C6 and decisions D1–D8 in the Plan are preserved. |

---

## 0. Conventions

### 0.1 Repository layout

```
ca-final/
├── pyproject.toml                # uv workspace root
├── docker-compose.yml            # postgres only
├── .env.example                  # GEMINI_API_KEY, DB passwords
├── config/
│   ├── settings.toml  sources.toml  models.toml  depth.toml  scoring.toml
├── taxonomy/                     # L0 taxonomy-as-code (source of truth for ref.*)
│   ├── registry/  schemes.yaml attempts.yaml papers.yaml doc_types.yaml instruments.yaml law_boundaries.yaml
│   ├── papers/    P1.yaml … P6.yaml           # tree + stable IDs
│   ├── descriptors/ P1.yaml … P6.yaml         # descriptions, keywords, anchors
│   ├── weightage/ P1.yaml … P6.yaml
│   └── applicability/ 2026-05.yaml …          # per-attempt study-guideline rules
├── profiles/                     # L2 extraction profiles
├── overrides/                    # L2 per-document manual overrides (by sha256)
├── prompts/                      # L3 prompts, versioned filenames
├── packages/
│   ├── contracts/   # Pydantic models for C0–C6 (no I/O)
│   ├── db/          # SQLAlchemy models, Alembic migrations, role grants
│   ├── common/      # settings, logging, run context, LLM client, blob store
│   ├── l0_taxonomy/ l1_acquire/ l2_extract/ l3_classify/ l4_curate/ l5_intel/
│   ├── api/         # FastAPI app (L6 backend)
│   └── cli/         # `caf` Typer entrypoint
├── web/                          # React + Vite + TS (L6 frontend)
├── tests/ fixtures/ (private PDFs, expected YAML)
└── data/  (git-ignored) blobs/ inbox/ debug/ logs/ backups/ browser-profile/
```

### 0.2 Toolchain

**Backend (pin everything in lockfiles):**

| Area | Tools |
|---|---|
| Runtime & packaging | Python 3.12, `uv` |
| Lint, types, tests | `ruff`, `mypy` (strict for `contracts`), `pytest` |
| Data access | `sqlalchemy` 2.x, `alembic`, `psycopg` 3, `pydantic` 2, `pydantic-settings` |
| CLI & logging | `typer`, `structlog` |
| Fetching | `httpx`, `selectolax`, `playwright` |
| PDF & OCR | `pymupdf`, `ocrmypdf` + Tesseract (`eng`) |
| Similarity | `rapidfuzz`, `datasketch` |
| LLM | `google-genai` |
| Server | `fastapi`, `uvicorn` |

**Frontend:** Node LTS, `pnpm`, Vite, React, TypeScript, TanStack Query, React Router, `openapi-typescript` + `openapi-fetch`, Vitest, Playwright.

**Licensing note.** PyMuPDF is AGPL. That is fine for a private, single-user tool. If the app is ever hosted for others, AGPL network-use obligations apply — at that point either swap to `pypdfium2` or comply.

### 0.3 Identity and time conventions

| Entity | ID format |
|---|---|
| Attempts | `YYYY-MM` of the exam month (e.g., `2025-09`). The ID is independent of scheme, because old- and new-scheme exams can run in the same attempt. |
| Schemes | `pre2017`, `s2017`, `s2023` (verify names/boundaries in M0) |
| Papers | `<scheme>.<code>`, e.g., `s2023.P4` |
| Taxonomy nodes | `<PaperCode>-<6 Crockford base32 chars>`, e.g., `P1-7KQ2MX`. Generated once by bootstrap, **never** changed or reused. |

- All timestamps are `timestamptz`, stored in UTC and displayed in Asia/Kolkata.
- Block IDs in L2 are `p{page}-b{index}` — stable for the same PDF bytes with the same PyMuPDF version (recorded in the extract run).

### 0.4 Run context (applies to every offline command)

Every `caf` command that writes data opens a **run**:

1. Insert `ops.run` with stage, git SHA, config hash and args.
2. Pass `run_id` to every write.
3. Close with status `ok` | `partial` | `failed` | `aborted_budget`.

`partial` means some items failed but were recorded, and the command is safe to re-run.

---

## 1. Database

### 1.1 Local Postgres

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    environment: { POSTGRES_PASSWORD: ${PG_SUPERUSER_PASSWORD}, POSTGRES_DB: caf }
    ports: ["127.0.0.1:5433:5432"]
    volumes: ["./data/pg:/var/lib/postgresql/data"]
```

Migrations live in `packages/db/alembic`. The first migration creates the schemas, the roles (`caf_pipeline`, `caf_curator`, `caf_app`) and the grants listed in Plan §3.3. Grants are re-applied idempotently by `caf db grants`.

### 1.2 DDL (authoritative shape; Alembic implements it)

```sql
CREATE SCHEMA ref; CREATE SCHEMA ingest; CREATE SCHEMA core;
CREATE SCHEMA intel; CREATE SCHEMA app; CREATE SCHEMA ops;

-- ============ ops ============
CREATE TABLE ops.run (
  id bigserial PRIMARY KEY,
  stage text NOT NULL,                 -- 'l0.load','l1.discover','l1.fetch','l2.extract','l3.classify','l4.publish','l5.score',...
  git_sha text, config_hash text, args jsonb,
  started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  status text NOT NULL DEFAULT 'running'
    CHECK (status IN ('running','ok','partial','failed','aborted_budget')),
  stats jsonb NOT NULL DEFAULT '{}', error text);

CREATE TABLE ops.llm_call (
  id bigserial PRIMARY KEY, run_id bigint NOT NULL REFERENCES ops.run(id),
  task text NOT NULL, model_id text NOT NULL, prompt_version text NOT NULL,
  input_tokens int, output_tokens int, cached_tokens int, cost_usd numeric(10,5),
  latency_ms int, status text NOT NULL CHECK (status IN ('ok','retry','schema_error','error')),
  error text, batch_job_id text, at timestamptz NOT NULL DEFAULT now());

CREATE TABLE ops.event (
  id bigserial PRIMARY KEY, run_id bigint REFERENCES ops.run(id),
  level text NOT NULL CHECK (level IN ('info','warn','error','alarm')),
  code text NOT NULL,                  -- e.g. 'L1_ZERO_LINKS', 'L2_V3_MARKS_MISMATCH'
  message text NOT NULL, context jsonb, at timestamptz NOT NULL DEFAULT now());

-- ============ ref (written only by the L0 loader) ============
CREATE TABLE ref.taxonomy_version (
  id serial PRIMARY KEY, git_sha text, yaml_hash text NOT NULL,
  loaded_at timestamptz NOT NULL DEFAULT now(), notes text);

CREATE TABLE ref.scheme (id text PRIMARY KEY, name text NOT NULL, notes text);

CREATE TABLE ref.attempt (
  id text PRIMARY KEY,                             -- '2025-09'
  exam_year int NOT NULL, exam_month int NOT NULL CHECK (exam_month BETWEEN 1 AND 12),
  label text NOT NULL, exam_start_date date, verified boolean NOT NULL DEFAULT false,
  UNIQUE (exam_year, exam_month));

CREATE TABLE ref.paper (
  id text PRIMARY KEY, scheme_id text NOT NULL REFERENCES ref.scheme(id),
  code text NOT NULL, name text NOT NULL, group_no int,
  max_marks int NOT NULL DEFAULT 100, is_current boolean NOT NULL DEFAULT false,
  UNIQUE (scheme_id, code));

CREATE TABLE ref.doc_type (
  id text PRIMARY KEY,   -- question_paper, suggested_answer, rtp, mtp_question, mtp_answer,
                         -- case_scenarios, ibs_case_study, study_material, study_guidelines,
                         -- weightage, syllabus, saransh, examiner_comments
  signal_class text NOT NULL CHECK (signal_class IN ('exam','practice','reference')),
  has_questions boolean NOT NULL, has_answers boolean NOT NULL, description text);

CREATE TABLE ref.node (
  id text PRIMARY KEY,
  paper_id text NOT NULL REFERENCES ref.paper(id),
  parent_id text REFERENCES ref.node(id),
  level text NOT NULL CHECK (level IN ('chapter','topic','subtopic')),
  name text NOT NULL, seq int NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','deprecated')),
  sm_ref text, sm_pages int4range,
  created_in int REFERENCES ref.taxonomy_version(id),
  updated_in int REFERENCES ref.taxonomy_version(id),
  CHECK ((level = 'chapter') = (parent_id IS NULL)));
CREATE INDEX ON ref.node (parent_id);  CREATE INDEX ON ref.node (paper_id, level);

CREATE TABLE ref.descriptor (
  node_id text PRIMARY KEY REFERENCES ref.node(id),
  description text NOT NULL, keywords text[] NOT NULL DEFAULT '{}',
  approved boolean NOT NULL DEFAULT false,
  source text NOT NULL CHECK (source IN ('llm_draft','curator')));

CREATE TABLE ref.instrument (
  id text PRIMARY KEY,         -- IndAS, AS, SA, SQC, SQM, SRE, SAE, SRS, ITA1961, ITA2025, CGST, IGST, CUSTOMS, FTP, ...
  name text NOT NULL, paper_codes text[] NOT NULL);

CREATE TABLE ref.anchor (
  id bigserial PRIMARY KEY,
  instrument_id text NOT NULL REFERENCES ref.instrument(id),
  ref_key text NOT NULL,       -- normalised: '116', '80C', '10(10D)', '16(2)'
  node_id text NOT NULL REFERENCES ref.node(id),
  weight real NOT NULL DEFAULT 1.0,
  UNIQUE (instrument_id, ref_key, node_id));
CREATE INDEX ON ref.anchor (instrument_id, ref_key);

CREATE TABLE ref.weightage_section (
  id text PRIMARY KEY, paper_id text NOT NULL REFERENCES ref.paper(id),
  name text NOT NULL, min_pct numeric NOT NULL, max_pct numeric NOT NULL,
  valid_from_attempt text REFERENCES ref.attempt(id));
CREATE TABLE ref.weightage_member (
  section_id text REFERENCES ref.weightage_section(id),
  chapter_id text REFERENCES ref.node(id), PRIMARY KEY (section_id, chapter_id));

CREATE TABLE ref.applicability_rule (
  id bigserial PRIMARY KEY, attempt_id text NOT NULL REFERENCES ref.attempt(id),
  node_id text NOT NULL REFERENCES ref.node(id),
  effect text NOT NULL CHECK (effect IN ('exclude','include')),
  source_note text);

CREATE TABLE ref.law_boundary (
  id text PRIMARY KEY, paper_code text NOT NULL, instrument_id text REFERENCES ref.instrument(id),
  first_applicable_attempt text REFERENCES ref.attempt(id),
  scope_node_ids text[],       -- null = whole paper
  policy text NOT NULL CHECK (policy IN ('mark_stale','exclude')), description text);

CREATE TABLE ref.node_version_link (
  id bigserial PRIMARY KEY, old_node_id text NOT NULL REFERENCES ref.node(id),
  new_node_id text NOT NULL REFERENCES ref.node(id),
  relation text NOT NULL CHECK (relation IN ('split_into','merged_into','moved')),
  taxonomy_version_id int NOT NULL REFERENCES ref.taxonomy_version(id));

-- ============ ingest (pipeline-owned staging) ============
CREATE TABLE ingest.source_page (
  id bigserial PRIMARY KEY, source_id text NOT NULL, url text UNIQUE NOT NULL,
  depth int NOT NULL, parent_page_id bigint REFERENCES ingest.source_page(id),
  fetch_mode text NOT NULL CHECK (fetch_mode IN ('http','browser','assisted')),
  robots_allowed boolean, last_fetched_at timestamptz, http_status int,
  etag text, last_modified text, link_count int, last_error text);

CREATE TABLE ingest.document (
  id bigserial PRIMARY KEY,
  sha256 char(64) UNIQUE NOT NULL, blob_path text NOT NULL, bytes bigint NOT NULL,
  origin text NOT NULL CHECK (origin IN ('http','browser','assisted','manual')),
  scheme_id text REFERENCES ref.scheme(id), attempt_id text REFERENCES ref.attempt(id),
  paper_id text REFERENCES ref.paper(id), doc_type_id text REFERENCES ref.doc_type(id),
  series text, part text, title text,
  chapter_hint_node_id text REFERENCES ref.node(id),       -- structure prior (L3 stage 0)
  catalog_status text NOT NULL DEFAULT 'inferred'
    CHECK (catalog_status IN ('inferred','needs_curation','confirmed','rejected')),
  extract_status text NOT NULL DEFAULT 'pending'
    CHECK (extract_status IN ('pending','running','ok','ok_with_warnings','needs_review','failed','not_applicable')),
  extract_run_id bigint REFERENCES ops.run(id),
  page_count int, has_text_layer boolean, ocr_sha256 char(64),
  supersedes_document_id bigint REFERENCES ingest.document(id),
  superseded boolean NOT NULL DEFAULT false,
  depth_band text,                                         -- e.g. 's2017:2019' for Depth Gate bookkeeping
  created_run_id bigint REFERENCES ops.run(id), created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON ingest.document (catalog_status, extract_status);
CREATE INDEX ON ingest.document (attempt_id, paper_id, doc_type_id);

CREATE TABLE ingest.discovered_link (
  id bigserial PRIMARY KEY, url text UNIQUE NOT NULL,
  source_page_id bigint REFERENCES ingest.source_page(id),
  anchor_text text, breadcrumb text[], inferred jsonb NOT NULL DEFAULT '{}',
  link_status text NOT NULL DEFAULT 'new'
    CHECK (link_status IN ('new','downloaded','failed','manual_required','ignored','not_pdf')),
  document_id bigint REFERENCES ingest.document(id),
  tries int NOT NULL DEFAULT 0, next_try_at timestamptz, last_error text,
  first_seen_at timestamptz NOT NULL DEFAULT now(), last_checked_at timestamptz);

CREATE TABLE ingest.unit (
  id bigserial PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES ingest.document(id),
  extract_run_id bigint NOT NULL REFERENCES ops.run(id),
  parent_unit_id bigint REFERENCES ingest.unit(id),
  label_path text NOT NULL,                       -- 'Q2', 'Q2.a', 'Q2.a.ii', 'CS1', 'CS1.M3'
  display_label text NOT NULL,                    -- 'Q2(a)(ii)'
  kind text NOT NULL CHECK (kind IN ('case_stem','question','part','subpart','mcq')),
  is_gradable boolean NOT NULL,
  marks int CHECK (marks IS NULL OR marks BETWEEN 0 AND 100),
  marks_source text CHECK (marks_source IN ('explicit','summed','mcq_default','override','llm_ids')),
  choice_role text CHECK (choice_role IN ('compulsory','optional','unknown')),
  or_group text,
  page_start int NOT NULL, page_end int NOT NULL,
  block_start text NOT NULL, block_end text NOT NULL,
  question_text text NOT NULL,
  text_origin text NOT NULL CHECK (text_origin IN ('pdf','ocr','llm_transcribed')),
  fingerprint char(40) NOT NULL,
  parse_confidence text NOT NULL CHECK (parse_confidence IN ('high','medium','low')),
  validation_flags text[] NOT NULL DEFAULT '{}',
  classify_status text NOT NULL DEFAULT 'pending'
    CHECK (classify_status IN ('pending','running','suggested','failed','skipped','decided','excluded')),
  current boolean NOT NULL DEFAULT true,
  UNIQUE (document_id, extract_run_id, label_path));
CREATE INDEX ON ingest.unit (fingerprint);
CREATE INDEX ON ingest.unit (classify_status) WHERE current AND is_gradable;

CREATE TABLE ingest.unit_answer (
  unit_id bigint PRIMARY KEY REFERENCES ingest.unit(id),
  answer_document_id bigint NOT NULL REFERENCES ingest.document(id),
  answer_text text, page_start int, page_end int, mcq_correct_option char(1),
  pairing_method text NOT NULL CHECK (pairing_method IN ('same_doc','cross_doc','mcq_key','override')));

CREATE TABLE ingest.tag_suggestion (
  id bigserial PRIMARY KEY, unit_id bigint NOT NULL REFERENCES ingest.unit(id),
  run_id bigint NOT NULL REFERENCES ops.run(id),
  node_id text NOT NULL REFERENCES ref.node(id),
  role text NOT NULL CHECK (role IN ('primary','secondary')),
  method text NOT NULL CHECK (method IN ('structure','anchor','llm','duplicate')),
  bucket char(1) NOT NULL CHECK (bucket IN ('A','B','C','D')),
  evidence jsonb NOT NULL,   -- {votes:[...], anchors:[...], justification:"...", alternatives:[...]}
  model_id text, prompt_version text, is_shadow boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON ingest.tag_suggestion (unit_id, is_shadow);

CREATE TABLE ingest.unit_gist (
  unit_id bigint NOT NULL REFERENCES ingest.unit(id), run_id bigint NOT NULL REFERENCES ops.run(id),
  gist text NOT NULL CHECK (char_length(gist) <= 220), model_id text,
  PRIMARY KEY (unit_id, run_id));

CREATE TABLE ingest.taxonomy_gap (
  id bigserial PRIMARY KEY, unit_id bigint NOT NULL REFERENCES ingest.unit(id),
  run_id bigint REFERENCES ops.run(id), proposed_parent_id text REFERENCES ref.node(id),
  proposed_name text, note text,
  status text NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','resolved_new_node','resolved_existing','ignored')));

CREATE TABLE ingest.duplicate_link (
  unit_id bigint REFERENCES ingest.unit(id), other_unit_id bigint REFERENCES ingest.unit(id),
  similarity real NOT NULL, PRIMARY KEY (unit_id, other_unit_id));

-- ============ core (published knowledge; written only via L4) ============
CREATE TABLE core.appearance (
  id bigserial PRIMARY KEY,
  unit_fingerprint char(40) UNIQUE NOT NULL,
  source_unit_id bigint,                          -- informational; ingest may be rebuilt
  doc_sha256 char(64) NOT NULL,                   -- stable document key
  attempt_id text NOT NULL REFERENCES ref.attempt(id),
  source_paper_id text NOT NULL REFERENCES ref.paper(id),
  doc_type_id text NOT NULL REFERENCES ref.doc_type(id),
  signal_class text NOT NULL CHECK (signal_class IN ('exam','practice')),
  series text, display_label text NOT NULL, marks int,
  gist text NOT NULL,
  official_url text, official_url_dead boolean NOT NULL DEFAULT false,
  page_start int NOT NULL, page_end int NOT NULL,
  law_stale boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'published' CHECK (status IN ('published','orphaned','withdrawn')),
  duplicate_of bigint REFERENCES core.appearance(id),
  published_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON core.appearance (attempt_id, signal_class) WHERE status = 'published';

CREATE TABLE core.appearance_tag (
  appearance_id bigint NOT NULL REFERENCES core.appearance(id) ON DELETE CASCADE,
  node_id text NOT NULL REFERENCES ref.node(id),
  role text NOT NULL CHECK (role IN ('primary','secondary')),
  share real NOT NULL CHECK (share > 0 AND share <= 1),
  decision_id bigint NOT NULL, PRIMARY KEY (appearance_id, node_id));
CREATE INDEX ON core.appearance_tag (node_id);

CREATE TABLE core.decision (
  id bigserial PRIMARY KEY, unit_fingerprint char(40) NOT NULL,
  action text NOT NULL CHECK (action IN ('accept','accept_alt','edit','none_fits','exclude','bulk_accept','undo')),
  payload jsonb NOT NULL,            -- final tags, gist, suggestion ids shown
  suggestion_run_id bigint, blind boolean NOT NULL DEFAULT false,
  seconds_spent real, decided_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON core.decision (unit_fingerprint, decided_at DESC);

CREATE TABLE core.change_log (
  id bigserial PRIMARY KEY, entity text NOT NULL, entity_id text NOT NULL,
  change text NOT NULL, before jsonb, after jsonb, reason text,
  at timestamptz NOT NULL DEFAULT now());

-- ============ intel (derived; written only by L5) ============
CREATE TABLE intel.score_run (
  id bigserial PRIMARY KEY, scoring_version text NOT NULL, config_hash text NOT NULL,
  target_attempt_id text NOT NULL REFERENCES ref.attempt(id),
  shadow boolean NOT NULL DEFAULT false, is_current boolean NOT NULL DEFAULT false,
  status text NOT NULL CHECK (status IN ('running','ok','failed')),
  started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
CREATE UNIQUE INDEX one_current_run ON intel.score_run (is_current) WHERE is_current AND NOT shadow;

CREATE TABLE intel.subtopic_score (
  score_run_id bigint NOT NULL REFERENCES intel.score_run(id) ON DELETE CASCADE,
  node_id text NOT NULL REFERENCES ref.node(id),
  applicable boolean NOT NULL,
  exam_score real NOT NULL, practice_score real NOT NULL, weight_prior real NOT NULL,
  importance real NOT NULL, freq_hits int NOT NULL, freq_window int NOT NULL,
  exam_marks_total int NOT NULL, exam_count int NOT NULL, practice_count int NOT NULL,
  first_exam_attempt text, last_exam_attempt text,
  PRIMARY KEY (score_run_id, node_id));

CREATE TABLE intel.ingestion_coverage (
  score_run_id bigint NOT NULL REFERENCES intel.score_run(id) ON DELETE CASCADE,
  paper_id text NOT NULL, attempt_id text NOT NULL,
  exam_published boolean NOT NULL, practice_published boolean NOT NULL,
  PRIMARY KEY (score_run_id, paper_id, attempt_id));

CREATE TABLE intel.depth_gate_report (
  id bigserial PRIMARY KEY, paper_code text NOT NULL, band text NOT NULL,
  baseline_run_id bigint REFERENCES intel.score_run(id), shadow_run_id bigint REFERENCES intel.score_run(id),
  top_k int NOT NULL, jaccard real, spearman real, newly_asked_nodes int,
  units_to_review int, est_review_hours real, created_at timestamptz NOT NULL DEFAULT now(),
  decision text CHECK (decision IN ('continue','continue_practice_value','stop')), decided_note text);

-- ============ app (user data; irreplaceable) ============
CREATE TABLE app.user_account (id smallint PRIMARY KEY, name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());   -- exactly one row in Phase 1

CREATE TABLE app.settings (
  user_id smallint PRIMARY KEY REFERENCES app.user_account(id),
  target_attempt_id text REFERENCES ref.attempt(id), exam_start_date date,
  hours_per_week numeric(5,1) NOT NULL DEFAULT 20, minutes_per_subtopic int NOT NULL DEFAULT 45,
  revision_intervals int[] NOT NULL DEFAULT '{3,7,21,60}');

CREATE TABLE app.progress (
  user_id smallint NOT NULL REFERENCES app.user_account(id),
  node_id text NOT NULL REFERENCES ref.node(id),
  status text NOT NULL CHECK (status IN ('not_started','in_progress','done')),
  status_changed_at timestamptz NOT NULL DEFAULT now(),
  first_done_at timestamptz, last_revised_at timestamptz,
  verify_flag boolean NOT NULL DEFAULT false,    -- set by taxonomy splits/merges
  PRIMARY KEY (user_id, node_id));               -- missing row = not_started

CREATE TABLE app.progress_event (
  id bigserial PRIMARY KEY, user_id smallint NOT NULL, node_id text NOT NULL REFERENCES ref.node(id),
  from_status text, to_status text NOT NULL, at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ON app.progress_event (user_id, at);

CREATE TABLE app.note (
  user_id smallint NOT NULL, node_id text NOT NULL REFERENCES ref.node(id),
  body text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED,
  PRIMARY KEY (user_id, node_id));
CREATE INDEX ON app.note USING gin (tsv);

CREATE TABLE app.revision_event (
  id bigserial PRIMARY KEY, user_id smallint NOT NULL, node_id text NOT NULL REFERENCES ref.node(id),
  outcome text NOT NULL CHECK (outcome IN ('ok','shaky')), at timestamptz NOT NULL DEFAULT now());

CREATE TABLE app.mock_test (
  id bigserial PRIMARY KEY, user_id smallint NOT NULL, paper_id text NOT NULL REFERENCES ref.paper(id),
  attempt_id text REFERENCES ref.attempt(id), label text, score numeric(5,1) NOT NULL,
  max_score numeric(5,1) NOT NULL CHECK (max_score > 0), taken_on date NOT NULL, notes text);

CREATE TABLE app.study_session (
  id bigserial PRIMARY KEY, user_id smallint NOT NULL, node_id text REFERENCES ref.node(id),
  started_at timestamptz NOT NULL, ended_at timestamptz, minutes int);
```

Full-text search for taxonomy and gists uses expression GIN indexes on `ref.node.name || ref.descriptor.description` and `core.appearance.gist`.

**Why `core` has no foreign keys into `ingest`.** `ingest` must be rebuildable (drop and re-run) without touching published knowledge. The join key between the two is the **fingerprint**, not the row ID.

### 1.3 Contracts package (C0–C6 in code)

`packages/contracts` holds Pydantic models that mirror each contract. Every layer's public function signatures use only these types. Excerpt:

```python
from pydantic import BaseModel, Field, constr
from typing import Literal

AttemptId = constr(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
NodeId    = constr(pattern=r"^P[1-6]-[0-9A-HJKMNP-TV-Z]{6}$")

class DocumentRecord(BaseModel):                      # C1
    id: int; sha256: str; blob_path: str
    scheme_id: str; attempt_id: AttemptId; paper_id: str
    doc_type_id: str; series: str | None; part: str | None
    catalog_status: Literal["confirmed"]              # readiness predicate encoded in type

class UnitRecord(BaseModel):                          # C2
    id: int; document_id: int; label_path: str; display_label: str
    kind: Literal["case_stem","question","part","subpart","mcq"]
    is_gradable: bool; marks: int | None
    page_start: int; page_end: int; question_text: str
    answer_text: str | None; context_text: str | None  # case stem for MCQs
    fingerprint: str; parse_confidence: Literal["high","medium","low"]

class TagSuggestion(BaseModel):                       # C3
    unit_id: int; node_id: NodeId; role: Literal["primary","secondary"]
    method: Literal["structure","anchor","llm","duplicate"]
    bucket: Literal["A","B","C","D"]; evidence: dict
    model_id: str | None; prompt_version: str | None

class PublishedAppearance(BaseModel):                 # C4
    unit_fingerprint: str; attempt_id: AttemptId; source_paper_id: str
    doc_type_id: str; signal_class: Literal["exam","practice"]
    display_label: str; marks: int | None; gist: str = Field(max_length=220)
    official_url: str | None; page_start: int; page_end: int; law_stale: bool
    tags: list[tuple[NodeId, Literal["primary","secondary"], float]]
```

Contract tests in `tests/contracts/` assert that every invariant listed in Plan §4 holds against a seeded database: stable node IDs, no `core` row without a decision, no deprecated node in `intel` as applicable, and so on.

---

## 2. L0 — Reference & Taxonomy

### 2.1 Registry files

These files are plain data, verified against ICAI sources, and each entry carries `verified: true|false`.

```yaml
# taxonomy/registry/attempts.yaml
- {id: "2024-05", label: "May 2024", verified: false}
- {id: "2024-11", label: "Nov 2024", verified: false}
- {id: "2025-05", label: "May 2025", verified: false}
- {id: "2025-09", label: "Sept 2025", verified: false}
- {id: "2026-01", label: "Jan 2026", verified: false}
- {id: "2026-05", label: "May 2026", verified: false}
# older attempts appended as Depth Gate bands are opened
```

```yaml
# taxonomy/registry/doc_types.yaml
- {id: question_paper,   signal_class: exam,      has_questions: true,  has_answers: false}
- {id: suggested_answer, signal_class: exam,      has_questions: true,  has_answers: true}
- {id: rtp,              signal_class: practice,  has_questions: true,  has_answers: true}
- {id: mtp_question,     signal_class: practice,  has_questions: true,  has_answers: false}
- {id: mtp_answer,       signal_class: practice,  has_questions: true,  has_answers: true}
- {id: case_scenarios,   signal_class: practice,  has_questions: true,  has_answers: true}
- {id: ibs_case_study,   signal_class: practice,  has_questions: true,  has_answers: true}
- {id: study_material,   signal_class: reference, has_questions: false, has_answers: false}
- {id: study_guidelines, signal_class: reference, has_questions: false, has_answers: false}
- {id: weightage,        signal_class: reference, has_questions: false, has_answers: false}
- {id: syllabus,         signal_class: reference, has_questions: false, has_answers: false}
- {id: saransh,          signal_class: reference, has_questions: false, has_answers: false}
```

```yaml
# taxonomy/registry/law_boundaries.yaml
- id: gst_intro
  paper_code: P5
  instrument_id: CGST
  first_applicable_attempt: "2018-05"      # VERIFY
  scope_node_ids: null                     # null = whole paper; list Customs/FTP chapters to exempt via 'exempt_node_ids'
  exempt_node_ids: []                      # fill with Customs & FTP chapter IDs
  policy: exclude
- id: ita_2025
  paper_code: P4
  instrument_id: ITA2025
  first_applicable_attempt: null           # VERIFY from ICAI Study Guidelines
  policy: mark_stale
```

### 2.2 Taxonomy file format

```yaml
# taxonomy/papers/P1.yaml
paper: s2023.P1
sm_edition: "Applicable for May 2026 onwards"   # study material edition used
chapters:
  - id: P1-3F9K2A
    name: "Ind AS 116: Leases"
    sm_ref: "Module 3, Chapter 9"
    sm_pages: [412, 470]
    topics:
      - id: P1-8H2M4Q
        name: "Lessee accounting"
        subtopics:
          - {id: P1-Q7T1ZC, name: "Initial measurement of ROU asset and lease liability", sm_pages: [418, 423]}
          - {id: P1-R2V9KD, name: "Lease modifications (lessee)", sm_pages: [431, 436]}
migrations: []        # see §2.6
```

```yaml
# taxonomy/descriptors/P1.yaml
P1-R2V9KD:
  description: "Accounting by a lessee when lease scope or consideration changes: separate lease vs remeasurement, revised discount rate, ROU adjustment and gain/loss on scope decrease."
  keywords: [lease modification, remeasurement, revised discount rate, decrease in scope]
  anchors: ["IndAS:116"]
  approved: true
```

Chapters and topics also get descriptors, which the chapter step of L3 uses. The tree file and the descriptor file are kept separate so that structural diffs stay readable.

### 2.3 Bootstrap procedure (`caf taxonomy bootstrap --paper P1`)

**Inputs.** The confirmed `study_material` documents for the paper (from L1).

**Step 1 — Outline extraction.** For each study-material PDF, call `doc.get_toc(simple=False)`. If the TOC has ≥10 entries and at least two levels, use it.

**Step 2 — Fallback heading detection** (TOC missing or flat):
1. Collect all spans with font size, bold flag, and text.
2. Take the body font size to be the mode.
3. A heading candidate is a line where either:
   - size ≥ body + 1pt, or
   - it is bold, starts the line, and matches `^\d+(\.\d+){0,3}\s+\S`.
4. Assign levels by numbering depth (`1.` → L1, `1.2` → L2, `1.2.3` → L3). If there is no numbering, rank by font size.
5. Drop boilerplate headings using a stoplist: *Learning Outcomes, Chapter Overview, Introduction* (only when it is the sole L1), *Summary, Test Your Knowledge, Answers, Illustration \d+, Case Study, Annexure, Significant Points, Let us Recapitulate*.

**Step 3 — Level mapping.**

| Study-material structure | Taxonomy level |
|---|---|
| SM chapter | chapter |
| Numbered L1 section | topic |
| Numbered L2 section | subtopic |

If a topic has no L2 sections, it gets a single subtopic with the same name. Numbered L3 sections become subtopics only when their parent L2 section is longer than 8 pages.

**Step 4 — Granularity guard (report, don't auto-fix).**

| Condition | Reported as |
|---|---|
| Chapter with >40 subtopics | `too_fine` |
| Chapter with <8 subtopics and >25 pages | `too_coarse` |
| Subtopic spanning >10 pages | `oversized` |

**Step 5 — Emit a draft YAML.** New nodes get generated IDs. Existing IDs are **reused** when a name matches an existing node under the same parent (similarity ≥0.9), so re-running bootstrap never churns IDs.

**Step 6 — Curator editing.** The curator edits the YAML by hand: merges trivia, splits bloated nodes, renames for clarity, and reorders. Typical budget: 2–4 hours per paper.

### 2.4 Descriptor drafting (`caf taxonomy describe --paper P1`)

For each active chapter, topic and subtopic that lacks an approved descriptor:

1. Extract the study-material text for `sm_pages`, capped at about 6,000 tokens (take the leading portion).
2. Run the deterministic anchor regexes (§5.3) over that text to collect candidate anchors with their frequency.
3. Call the LLM with task `l0.describe` and prompt `prompts/l0_describe.v1.md`.
   - **Input:** node path, node name, section text, candidate anchors.
   - **Output schema:** `{description ≤40 words, keywords ≤8, central_anchors ⊆ candidates}`.
   - **Prompt rules:** describe what an examiner could test from this section; name concepts, not page contents; no copying of sentences.
4. Write the result to `descriptors/Px.yaml` with `approved: false`.
5. The curator reviews it (diff view in git or in the curator UI) and flips `approved: true`.

**Rule.** L3 refuses to classify against a paper where less than 100% of *active subtopics* have approved descriptors, unless `--allow-unapproved` is passed (dev only).

### 2.5 Anchor index construction

The index is built from `descriptors/*.yaml → anchors` and supplemented by hand-maintained instrument maps:

- `taxonomy/anchors/P4_sections.yaml` — section ranges to nodes, for both ITA1961 and ITA2025.
- `taxonomy/anchors/P5_sections.yaml` — CGST/IGST/Customs sections.

**Key normalisation:**
- Uppercase and strip spaces.
- A section key keeps its base and its first bracket: `10(10D)` → `10(10D)` and base `10`.
- Lookup tries the full key first, then the base.

Range syntax is allowed in the maps (`"ITA1961:80C-80U" → P4-…`); the loader expands ranges for numeric-alpha section sequences using an explicit ordered section list in `instruments.yaml`. Never infer section ordering programmatically.

### 2.6 Loader (`caf taxonomy load [--apply]`)

The loader runs these phases in order:

1. **Parse** all YAML under `taxonomy/`.
2. **Validate.** Any failure aborts before anything is written:
   - IDs are globally unique and match `NodeId`.
   - The level chain is chapter → topic → subtopic.
   - `seq` is unique within each parent.
   - Every node present in the DB is present in the YAML, or has a declared migration or `status: deprecated`. Otherwise the error is `NODE_DISAPPEARED`.
   - Anchors reference known instruments.
   - Every chapter belongs to exactly one weightage section.
   - Weightage `min ≤ max`, and the sum of midpoints per paper is within 90–110%. Outside that range is a warning, not an error, because ICAI ranges don't sum to exactly 100.
   - Applicability rules reference existing attempts and nodes.
   - Descriptors cover active subtopics (warning before M4, error after).
3. **Diff** against the DB and build a **plan** listing: added nodes, renamed nodes (same ID, new name), moved nodes (new parent), deprecated nodes, migrations, descriptor changes, anchor changes, and weightage/applicability changes.
4. **Print the plan.** Without `--apply`, stop here.
5. **Apply** in a single transaction:
   1. Insert `ref.taxonomy_version`.
   2. Upsert the `ref.*` tables.
   3. Execute migration handlers (§2.7).
   4. Commit.
   5. Trigger `caf intel recompute`.

### 2.7 Taxonomy migrations (declared in YAML, executed by L4 handlers)

```yaml
migrations:
  - op: split
    from: P1-R2V9KD
    into: [P1-AAAA11, P1-BBBB22]       # new nodes must also exist in the tree
    progress_policy: inherit_verify    # children copy parent status, verify_flag=true
  - op: merge
    from: [P1-CCCC33, P1-DDDD44]
    into: P1-CCCC33                    # target can be one of the sources
    progress_policy: min_status        # not_started < in_progress < done
  - op: move
    node: P1-EEEE55
    new_parent: P1-8H2M4Q
  - op: deprecate
    node: P1-FFFF66
```

**Handler behaviour:**

| Operation | Effect |
|---|---|
| **split** | Insert `node_version_link(split_into)` rows. Every `core.appearance_tag` pointing at the source is flagged: its appearance goes back into the review queue with reason `taxonomy_split`, and the old tag stays live until the new decision is made. Progress follows `progress_policy`. The source becomes `deprecated`. |
| **merge** | Repoint tags to the target (if both sources tag the same appearance, keep one tag and sum the shares, capped at 1). Progress follows `progress_policy`. Sources other than the target become `deprecated`. |
| **move** | Parent change only. No re-review. |
| **deprecate** | Node hidden from students. Tags stay for history and are excluded from scoring. Progress rows kept. |

Every handler writes a `core.change_log` entry.

### 2.8 Applicability and weightage ingestion

- **Study Guidelines.** For each attempt, the curator transcribes exclusions and inclusions into `taxonomy/applicability/<attempt>.yaml`, as node IDs plus a `source_note` quoting the guideline paragraph reference (not its text).
  - An LLM-assisted helper `caf taxonomy guidelines-draft --doc <id>` may propose node matches for each guideline line. The curator approves them.
- **Weightages.** The curator transcribes ICAI's section-wise table into `taxonomy/weightage/Px.yaml` (sections with min/max % and member chapters). This is a small, one-time job per syllabus revision.

**Applicability rule for target attempt `t`.** A node is applicable iff all of these hold:
- it is `active`;
- no `exclude` rule exists for `t` on the node or any ancestor, unless a more specific `include` rule applies;
- its paper is current.

### 2.9 L0 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| Bootstrap produces a flat or empty tree | PDF has no outline and headings aren't numbered | Run with `--heading-mode size`; inspect `data/debug/headings_<doc>.csv`; tune the size threshold per paper in `settings.toml` |
| `NODE_DISAPPEARED` on load | A node was deleted from YAML instead of deprecated or migrated | Restore it with `status: deprecated`, or declare a migration. **Never delete IDs.** |
| Same concept appears under two chapters | Study material repeats content (common in DT/IDT) | Keep one canonical subtopic and deprecate the other. Anchors will point to the canonical one. |
| L3 "none fits" rate >3% for a chapter | Granularity or coverage gap | Review `ingest.taxonomy_gap` for that chapter, add nodes or improve descriptors, reload, then re-run L3 for the gap units only |
| Weightage midpoint sum far from 100% | Transcription error or overlapping sections | Re-check against the ICAI PDF; each chapter must be in exactly one section |
| Study material revised mid-cycle (new edition) | ICAI amendment | Re-run bootstrap **in diff mode** (`--diff-only`): it reports new or removed headings against the current YAML; apply changes as normal edits and migrations |

---

## 3. L1 — Acquisition

### 3.1 Source registry

```toml
# config/sources.toml
[defaults]
user_agent = "CAFinalStudyCompanion/0.1 (personal study tool; contact: you@example.com)"
min_delay_s = 5
max_delay_s = 10
max_downloads_per_session = 200
pdf_hosts = ["resource.cdn.icai.org"]

[[source]]
id = "icai-final-pre2017"
url = "https://www.icai.org/post/final-course-old-scheme-of-education-and-training"
mode = "http"
scheme_hint = "pre2017"
max_depth = 2
follow_patterns = ["^https://www\\.icai\\.org/post"]

[[source]]
id = "bos-portal-final"
url = "https://boslive.icai.org/index.php"
mode = "browser"          # JS-rendered; Playwright for link discovery only
scheme_hint = "s2023"
max_depth = 3
follow_patterns = ["^https://boslive\\.icai\\.org/"]
```

Seed URLs for current-scheme exam papers, suggested answers, RTP and MTP pages are added in M2 after browsing the portal manually and recording their URLs. The file is data; the code never embeds URLs.

### 3.2 Robots and politeness

- For every host, fetch `robots.txt` once per run and evaluate it with `urllib.robotparser` against the configured User-Agent.
- A disallowed URL is **not fetched**. Its `source_page.robots_allowed=false` is recorded, and the page becomes an `assisted` task (`ops.event code=L1_ROBOTS_ASSISTED`).
- Delay between requests to the same host is uniformly random in `[min_delay_s, max_delay_s]`.
- `Retry-After` on 429/503 is honoured.
- At most one in-flight request per host.
- **Human checks.** If a response looks like a challenge — HTML where a PDF was expected, a challenge-page marker in the body, or 403 with a challenge header — stop the source immediately. Mark its remaining items `manual_required` and raise alarm `L1_HUMAN_CHECK`. Never retry past a challenge.

### 3.3 Discovery (`caf acquire discover [--source ID]`)

Breadth-first walk from each seed, up to `max_depth`:

```
queue ← [(seed, depth=0, breadcrumb=[])]
while queue:
    page, depth, crumbs ← pop
    if not robots_allowed(page): record assisted task; continue
    html ← fetch(page)  via httpx (mode=http) or Playwright page.content() after networkidle (mode=browser)
    for each <a href>:
        url ← absolutise + strip fragments
        if url is PDF (path ends .pdf or HEAD content-type application/pdf on pdf_hosts):
            upsert discovered_link(url, anchor_text, breadcrumb=crumbs+[page_title], inferred=infer(...))
        elif depth < max_depth and matches follow_patterns and not seen:
            push (url, depth+1, crumbs+[anchor_text])
    source_page.link_count ← number of PDF links on this page
    if link_count == 0 and previous link_count > 0:   ALARM L1_ZERO_LINKS (layout change)
```

### 3.4 Metadata inference

The input is `text = " | ".join(breadcrumb + [anchor_text, filename])`. Each field is resolved independently.

| Field | Rule |
|---|---|
| attempt | Regex `(?i)\b(jan(uary)?|may|june|july|sep(t(ember)?)?|nov(ember)?|dec(ember)?)\W{0,3}(20\d\d)\b`, mapped to `YYYY-MM` via a month table. Multiple distinct matches → ambiguous. |
| paper | Regex `(?i)paper\W{0,3}(\d)`, plus fuzzy match (rapidfuzz ≥85) of the text against paper names of the candidate scheme. The two must agree. |
| doc_type | Keyword table evaluated in order: `suggested answer` → `suggested_answer`; `question paper` → `question_paper`; `revision test paper\|\bRTP\b` → `rtp`; `mock test paper\|\bMTP\b` + `answer` → `mtp_answer`, else `mtp_question`; `case scenario` → `case_scenarios`; `study material` → `study_material`; `study guideline` → `study_guidelines`; `weightage` → `weightage`; `syllabus` → `syllabus`. |
| series | `(?i)series\W{0,3}(I{1,3}\|\d)` → "1"/"2" |
| scheme | Source `scheme_hint`, overridden by the paper-name match (e.g., "Strategic Financial Management" ⇒ `s2017` or `pre2017` depending on the year) |

- If every field resolves uniquely: `catalog_status = 'inferred'`.
- Otherwise: `catalog_status = 'needs_curation'`.
- **All exam and practice documents need confirmation regardless** (Plan §5.1).

### 3.5 Download (`caf acquire fetch [--limit N] [--attempt 2025-09 …]`)

**Selection.** `discovered_link.link_status IN ('new','failed') AND (next_try_at IS NULL OR next_try_at <= now())`, ordered by inferred attempt descending, then doc_type priority (`suggested_answer`, `question_paper`, `rtp`, `mtp_*`, `study_material`, others), then paper.

**Procedure for each link:**

1. Issue a conditional GET (`If-None-Match` / `If-Modified-Since` if known). Stream the body to `data/blobs/tmp/<uuid>` with a 60 s timeout and a 200 MB cap.
2. **Verify.** The body must start with `%PDF-`, `fitz.open()` must succeed, and `page_count` must be ≥1. On failure: `link_status='failed'` with error `NOT_PDF`/`CORRUPT_PDF`, and no retry unless the error was transient.
3. Compute SHA-256.
4. **Dedupe:**
   - If `ingest.document` already has that sha256, link the URL to that document (alias) and delete the temp file.
   - Else, if this URL was previously linked to a different document (content changed), create a new document with `supersedes_document_id` = old and set the old one's `superseded=true`. Raise event `L1_CONTENT_CHANGED` — the curator must decide whether published appearances from the old version need re-review. Default: re-extract, then reconcile via fingerprints (§6.4).
   - Else, create a new document.
5. Move the temp file atomically to `data/blobs/sha256/<aa>/<bb>/<sha>.pdf`.
6. Copy inferred metadata onto the document. `catalog_status` is `inferred` or `needs_curation`.

**Retry policy:**

| Condition | Action |
|---|---|
| Timeout / 5xx / 429 | Retry with backoff 5 s → 30 s → 120 s (`next_try_at`). After 3 tries: `failed`. |
| 404 / 410 | `failed` immediately. Event `L1_GONE`. If a published document had this URL, set `official_url_dead=true` (the L6 fallback serves the local copy). |
| 403 / challenge | `manual_required`. Stop the source (§3.2). |

### 3.6 Catalogue review (curator)

The curator UI (or `caf acquire catalog --tui`) lists documents with `catalog_status IN ('inferred','needs_curation')`, grouped by attempt. Columns: title, URL, inferred fields, and a thumbnail of page 1 (rendered on demand).

- Actions: edit fields, **confirm** (bulk selection allowed), reject (not relevant), and set `chapter_hint_node_id` (for chapter-organised documents).
- On confirm, validation checks that the fields are consistent with `ref`: the paper belongs to the scheme and the attempt exists. For `doc_type` in reference types, the document is routed to L0 tooling and gets `extract_status='not_applicable'`.

**Rule.** Only `confirmed` documents enter L2.

### 3.7 Assisted mode (`caf acquire assist --source ID | --url URL`)

1. Launch Playwright Chromium, **headed**, with a persistent profile at `data/browser-profile/`.
2. You navigate manually. The tool never clicks, types or solves anything.
3. Listeners:
   - `page.on("response")` records any response with `content-type: application/pdf`, plus its URL and the referring page title.
   - Every 3 s, the DOM is scanned for `a[href$=".pdf"]` and those links are recorded with the current page title as breadcrumb.
4. When you close the browser, the tool prints the count of new `discovered_link` rows.
5. Download the recorded links:
   - If the PDF host allows automated fetch, use the normal `fetch`.
   - Otherwise, use `caf acquire assist-download`, which opens each PDF URL in the same headed browser, one at a time, at the configured delay, while you are present.

### 3.8 Manual import (`caf acquire import data/inbox [--interactive]`)

- Accepts any PDF.
- Metadata comes from, in order:
  - a sidecar `<file>.meta.toml` (`attempt`, `paper`, `doc_type`, `series`, `scheme`, `url`);
  - the filename convention `S2023_P4_suggested_answer_2025-09.pdf`;
  - interactive prompts.
- Same verify/dedupe/store steps as §3.5, with `origin='manual'` and `catalog_status='inferred'`, so confirmation is still required.

### 3.9 Re-check cadence

Run `caf acquire discover` + `fetch`:

- monthly;
- immediately after ICAI announces RTPs/MTPs (about 2–3 months before an attempt);
- after suggested answers are released (a few weeks after an attempt).

Conditional GETs keep this cheap.

### 3.10 L1 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| `L1_ZERO_LINKS` alarm on a seed | Portal redesign or selector drift | Open the seed in a browser. Update `sources.toml` (new URL or `follow_patterns`). If JS-rendered now, switch `mode=browser`. Re-run discover. |
| `L1_HUMAN_CHECK` | Bot protection triggered | Stop. Do **not** retry. Use `assist` for that source. Lower your rate (raise `min_delay_s`) for future runs. |
| `L1_ROBOTS_ASSISTED` | Path disallowed by robots.txt | Use `assist` or manual import. Do not change the User-Agent to get around it. |
| Many `needs_curation` rows | Anchor text lacks attempt or paper info | Improve inference rules (add breadcrumb patterns), or bulk-edit in the catalogue UI. Never auto-confirm. |
| `L1_CONTENT_CHANGED` | ICAI replaced a PDF (errata or revision) | Let L2 re-extract. L4 reconciliation will flag changed units. Review only those. |
| `L1_GONE` for an already-published document | ICAI removed or moved the file | Nothing breaks: the local blob serves as the source. Optionally search the portal for the new URL and add it as an alias via the catalogue UI. |
| Duplicate documents with different metadata | Same PDF linked under two attempts or papers | Dedupe keeps one document. The catalogue UI shows the conflicting inferences; the curator picks the true metadata. |
| Disk usage growth | Study material volumes are large | Expected. Tens of GB at most. Blobs are never deleted, only backed up. |

---

## 4. L2 — Extraction

### 4.1 Pipeline per document (`caf extract run [--doc ID] [--profile ID] [--status pending]`)

```
select confirmed documents with extract_status IN ('pending') (or explicit --doc), ordered by value:
   signal_class=exam first, newest attempt first, then practice
for each document (independently; one failure never stops the batch):
   set extract_status='running'
   1 preflight           → text layer? OCR?
   2 block stream        → [Block]
   3 clean               → strip headers/footers, normalise
   4 profile select      → by (scheme, doc_type, paper) with fallback chain
   5 override check      → overrides/<sha256>.yaml wins if present
   6 segment             → unit tree (deterministic)
   7 pair answers        → same-doc or cross-doc
   8 validate            → flags + outcome
   9 LLM fallback        → only if outcome has hard errors and profile allows
  10 persist             → new units (current=true), old units current=false
  11 reconcile           → if doc has published appearances (§6.4)
   set extract_status = ok | ok_with_warnings | needs_review | failed
```

### 4.2 Preflight and OCR

1. Open with PyMuPDF. For each page, take `len(page.get_text("text").strip())`.
2. The document **has a text layer** if ≥70% of pages have ≥200 characters. Otherwise it is **scanned**.
3. Scanned documents: run `ocrmypdf --skip-text --output-type pdf -l eng --rotate-pages --deskew in.pdf out.pdf`. Store the output as a derived blob (`ocr_sha256`) and use it for all later steps. `text_origin='ocr'`.
4. **OCR quality check per page.** Compute the ratio of tokens found in a word list (English words plus a domain lexicon auto-built from study-material text). If the ratio is <0.75, the page is poor. Poor pages go through the vision fallback:
   - Render the page at 200 dpi.
   - Call the LLM with task `l2.transcribe` (Flash tier) and prompt "transcribe verbatim; preserve numbers, tables as pipe tables; output text only".
   - Replace that page's text with the transcription. Units touching the page get `text_origin='llm_transcribed'` and `parse_confidence` capped at `medium`.
   - Because students view the original page (D2), transcription errors can only affect classification — and every transcribed unit goes through review anyway.

### 4.3 Block stream and cleaning

1. For each page, call `page.get_text("dict", sort=True)`. Iterate blocks → lines → spans. Emit one `Line` per text line:
   `{block_id: "p{page}-b{i}", page, bbox, text, size (max span size), bold (any span with flags & 16), font}`.
2. **Header/footer removal.** Normalise each line (digits → `#`, collapse whitespace). If a normalised line occurs on ≥50% of pages, within the top or bottom 8% of page height, remove it everywhere. Also remove standalone page numbers.
3. **Normalisation:**
   - NFKC;
   - ligatures (`ﬁ` → `fi`);
   - Private-Use-Area rupee glyphs → `₹` (keep a table of observed codepoints per font in `profiles/glyph_map.yaml`);
   - dehyphenate `-\n` when both halves are alphabetic;
   - collapse runs of spaces.
   - **Never alter digits, decimal points, commas inside numbers, or brackets.**
4. **Tables.** No table reconstruction is needed for classification. Keep the line order from `sort=True`. (If a later feature needs tables, add `page.find_tables()` then — that is an additive change.)

### 4.4 Profiles

Profiles are YAML files. The selection chain: `(scheme, doc_type, paper)` → `(scheme, doc_type)` → `(doc_type)` → fail with `NO_PROFILE`.

```yaml
# profiles/s2023.suggested_answer.yaml
id: s2023.suggested_answer.v1
applies_to: {scheme: s2023, doc_type: suggested_answer}
paper_max: 100
patterns:
  question_start:
    - {re: '^\s*(?:QUESTION|Question)\s+(?P<n>\d{1,2})\b', require_bold: true}
  part_start:
    - {re: '^\s*\((?P<p>[a-h])\)\s+'}
  subpart_start:
    - {re: '^\s*\((?P<s>i{1,3}|iv|v|vi{0,3}|ix|x)\)\s+'}
  marks:
    - {re: '\((?P<m>\d{1,2})\s*Marks?\)'}
    - {re: '(?P<m>\d{1,2})\s*Marks\s*$'}
  answer_start:
    - {re: '^\s*(?:ANSWER|Answer)\b', require_bold: true}
  or_separator:
    - {re: '^\s*OR\s*$', require_bold: true}
  case_scenario_start:
    - {re: '^\s*CASE\s+SCENARIO\s*[-–]?\s*(?P<n>[IVX]+|\d+)', require_bold: true}
  mcq_start:
    - {re: '^\s*(?P<n>\d{1,2})\.\s+\S'}          # only inside a case scenario
  mcq_option:
    - {re: '^\s*\((?P<o>[A-Da-d])\)\s+'}
  mcq_key_table_title:
    - {re: '(?i)answers?\s+to\s+(?:the\s+)?(?:MCQ|multiple\s+choice)'}
  mcq_key_row:
    - {re: '^\s*(?P<n>\d{1,2})\s*[.)]?\s*\(?(?P<o>[A-Da-d])\)?\s*$'}
choice_rules:
  - {re: '(?i)question\s+no\.?\s*1\s+is\s+compulsory', set: {compulsory: ["Q1"]}}
  - {re: '(?i)(?:attempt|answer)\s+any\s+(?P<k>two|three|four|five|\d)\s+(?:questions\s+)?(?:out\s+)?of\s+the\s+remaining\s+(?P<n>two|three|four|five|six|\d)',
     set: {optional_pick: "{k}"}}
defaults:
  mcq_marks: 2                 # VERIFY per paper pattern
  min_unit_chars: 40
  max_unit_chars: 15000
mode: interleaved              # Q then its answer, per question (SA style)
```

Other modes:
- `sectioned` — all questions, then an "ANSWERS" section that repeats the numbering (some RTPs).
- `questions_only` — MTP question papers and question papers.

Profiles are **versioned**: `…v1`, `…v2`. Each extract run records the profile ID + version. Old-scheme eras get their own profiles (`s2017.*`, `pre2017.*`) — never overload one profile with era-specific branches.

### 4.5 Segmentation algorithm (deterministic)

State: a stack of open units `[question?, part?, subpart?]`, the current region (`question` | `answer`), and the current case scenario (if any).

```
for line in lines:
    kind ← first matching anchor in precedence order:
           case_scenario_start > question_start > or_separator > part_start > subpart_start
           > answer_start > mcq_start(only in case) > mcq_option > body
    match kind:
      case_scenario_start: close all; open case_stem(CS{n}); region=question
      question_start:      close all but case; open question(Q{n}); region=question
      part_start:          close part/subpart; open part(parent=question, label=p)
      subpart_start:       close subpart; open subpart(parent=part or question)
      or_separator:        mark next opened sibling with or_group = f"{parent}.or{k}"
      answer_start:        region=answer (answer text accrues to the deepest open unit)
      mcq_start:           open mcq(parent=case_stem, label=M{n}); region=question
      mcq_option:          append to current mcq; count options
      body:                append text to deepest open unit in current region
    if line matches marks pattern and region==question:
        attach marks to deepest open unit that has no marks yet; strip marks text from content
```

**Sectioned mode** runs two passes: questions first, then the answers section. Pairing is done by `label_path` (§4.6).

**Leaf and gradable determination:**
- A unit with explicit marks is gradable.
- A parent without marks whose children all have marks gets `marks=sum(children)`, `marks_source='summed'`, and is **not gradable** (the children are).
- A parent *with* marks whose children lack marks is gradable, and its children become non-gradable context.
- MCQs are gradable with `marks = explicit or defaults.mcq_marks`.
- Case stems are never gradable.

**Choice roles.** Apply the `choice_rules` found in the first two pages of instructions: `compulsory` for the listed questions, `optional` for the rest. If no rule is found, the role is `unknown`.

**Fingerprint:**
`sha1(doc_sha256 + "|" + label_path + "|" + normalise(question_text)[:200])`, where `normalise` = lowercase, drop non-alphanumerics, collapse spaces.

### 4.6 Answer pairing

| Case | Method |
|---|---|
| Same-doc, interleaved | Answer text accrues during segmentation. `pairing_method='same_doc'`. |
| Same-doc, sectioned | Match answer-section labels to question labels exactly. Unmatched labels on either side → validation flag `V4`. |
| Cross-doc (MTP question + MTP answer; QP + SA) | Find the sibling document with the same `(attempt, paper, series)` and the complementary `doc_type`. Match by `label_path`. For QP + SA, **prefer the SA document as the unit source** (it contains both). Units from the QP are used only to cross-check marks; disagreement → flag `V8_QP_SA_MARKS`. |
| MCQ keys | Parse the key table under `mcq_key_table_title`, map `n` → option, and attach to `CS{k}.M{n}`, using the order of case scenarios when numbering restarts per case. |

### 4.7 Validators

| Code | Check | Severity |
|---|---|---|
| V1 | Question numbers contiguous 1..N; parts contiguous a.. within each question (profile may whitelist gaps) | error |
| V2 | Every gradable unit has marks | error |
| V3 | Choice-aware total (below) | error if deviation > 2 marks, else warn |
| V4 | Every gradable unit in a doc with `has_answers` has an answer (or MCQ key) | error if >10% missing, else warn |
| V5 | Unit text length within `[min_unit_chars, max_unit_chars]` and below the profile's historical p99 × 1.5 | warn (error if > max) |
| V6 | MCQ has 4 options and a key | warn |
| V7 | Page spans monotonic; no overlapping units | error |
| V8 | QP/SA marks agreement | warn |

**V3 — attemptable maximum:**

```
groups   ← collapse each OR group to one virtual item with marks = max(alternatives)
comp     ← Σ marks of compulsory items (incl. all MCQ sections)
optional ← marks of optional items sorted desc
attemptable ← comp + Σ optional[:k]            # k from choice rule
if no choice rule: pass-with-warn if paper_max ≤ total ≤ 1.6 × paper_max else error
```

For Paper 6, a profile-level override applies: `attemptable = 4 × 25` (pick 4 of 5 case studies; verify).

**Outcome:**
- any error → `needs_review` (after trying the LLM fallback, if enabled);
- only warnings → `ok_with_warnings`;
- clean → `ok`.

`parse_confidence` per unit: `high` if no flags touch the unit, `medium` if warnings, `low` if errors.

### 4.8 LLM fallback segmenter (task `l2.segment`, Flash tier)

- **When:** `outcome` has errors and `profile.llm_fallback: true`.
- **Input:** a JSON list of lines `{id, page, text[:300], bold, size}` for the affected page range, chunked at about 40k tokens with a 2-page overlap. Also the profile's anchor examples and the expected paper structure (paper_max, choice rule).
- **Output schema:**

  ```json
  {"units":[{"label_path":"Q2.a","kind":"part","start":"p5-b3","end":"p6-b11",
             "marks":5,"marks_line":"p5-b3",
             "answer_start":"p6-b12","answer_end":"p8-b2"}]}
  ```

- **Acceptance** (all mandatory; otherwise discard the output):
  - every block ID exists;
  - ranges are ordered and non-overlapping;
  - `marks` appears literally in the text of `marks_line` and that line lies within the unit (anti-hallucination);
  - the rebuilt unit tree passes the same validators with no errors.
- Accepted output gets `marks_source='llm_ids'` and `parse_confidence` capped at `medium`. Text is still assembled by the code from the block IDs.

### 4.9 Overrides and the debug render

`caf extract debug --doc ID` writes two files:

- `data/debug/<sha>.html`: every line with its block ID, coloured by assigned unit, with unit labels, marks and flags in the margin.
- `data/debug/<sha>/p{n}.png`: page renders with unit bounding boxes drawn.

Override file example:

```yaml
# overrides/<sha256>.yaml
document_sha256: "…"
pymupdf_version: "1.24.x"      # loader warns if different from runtime
mode: patch                    # patch | replace
units:
  - label_path: Q4.b
    start: p9-b14
    end: p10-b3
    marks: 4
    answer_start: p10-b4
    answer_end: p11-b9
  - label_path: Q4.c           # delete a spurious unit
    delete: true
choice: {compulsory: ["Q1"], optional_pick: 4}
```

Overrides are applied after deterministic segmentation, and the result is re-validated. An override that yields validator errors fails loudly (`L2_OVERRIDE_INVALID`).

### 4.10 Profile development procedure (depth-first, per profile)

1. Pick 3 documents of the target profile spanning different papers and attempts.
2. Hand-write the expected output YAML (labels, marks, page spans) into `tests/fixtures/expected/<sha>.yaml`.
3. Iterate on the profile until `pytest -k extraction_golden` passes for all 3.
4. Run the profile on all documents of that type and read the validation report (`caf extract report --profile …`).
   - If >10% `needs_review`, add 2 more golden fixtures from the failures and iterate.
5. Declare the profile done when the Plan §5.2 DoD holds on a fresh sample of 3 unseen documents.

### 4.11 L2 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| `NO_PROFILE` | New doc type or era | Write a profile (§4.10). Don't force an existing one. |
| V1 errors across a whole attempt | Numbering style changed (e.g., "Q.1" vs "Question 1") | Add a pattern variant in a **new profile version**. Re-run for that attempt only. |
| V3 mismatch of exactly the MCQ total | MCQ marks default wrong for that paper | Set `mcq_marks` in a paper-specific profile. Verify against the paper's instructions. |
| V3 mismatch, choice rule not found | Instruction wording differs | Add a choice-rule regex, or set `choice` in an override. |
| Units merged (one very long unit) | Question heading not bold in that document, or `require_bold` too strict | Inspect the debug render. Relax `require_bold` in a doc-specific profile or override. |
| Scanned doc gives garbage even after OCR | Low-quality scan | Vision fallback runs automatically. If still failing, mark `needs_review` and use an override with page-range units. |
| Rupee or other symbols garbled | PUA glyph not mapped | Add the codepoint to `profiles/glyph_map.yaml`. Re-run the affected docs. |
| Re-extraction changes many fingerprints | Normalisation or profile change altered question text prefixes | Expected occasionally. L4 fuzzy reconciliation relinks most. Review only orphans. |
| LLM fallback repeatedly rejected | Model inventing ranges or marks | Leave it rejected — this is the safety net working. Use an override. |

---

## 5. L3 — Classification

### 5.1 Selection

Units are selected when all of these hold: `current AND is_gradable AND classify_status IN ('pending','failed')`, the document is confirmed with `extract_status IN ('ok','ok_with_warnings')` (the C2 readiness predicate — units of `needs_review` documents are never classified), and there is **no** `core.decision` for the unit's fingerprint.

Order: exam before practice, newest attempt first, then paper. Case-stem text is attached as `context_text` to its MCQs.

### 5.2 Stage 0 — Structure prior

If `document.chapter_hint_node_id` is set, candidate chapters = {hint}, and the chapter step is skipped. The suggestion's `method` includes `structure` in its evidence.

### 5.3 Stage 1 — Anchor extraction (deterministic)

Patterns run over `question_text + context_text + answer_text`:

| Instrument | Pattern (simplified) | Notes |
|---|---|---|
| IndAS | `\bInd\s*AS\s*(\d{1,3})\b` | |
| AS (Indian GAAP) | `(?<!Ind\s)\bAS\s*(\d{1,2})\b` | exclude "AS per", "AS on" by requiring a digit |
| SA / SQC / SQM / SRE / SAE / SRS | `\b(SA)\s*(\d{3})\b`, `\b(SQC|SQM)\s*(\d)\b`, `\b(SRE|SAE|SRS)\s*(\d{4})\b` | |
| Sections | `\b(?:[Ss]ection|[Ss]ec\.|u/s)\s*(\d{1,3}[A-Z]{0,4})(\(\w{1,4}\))?` | act resolved by context (below) |
| Rules | `\b[Rr]ule\s*(\d{1,3}[A-Z]?)` | paper-specific instrument (e.g., CGST Rules) |

**Act resolution for sections:**
- **P4:** ITA2025 if the text mentions "Income-tax Act, 2025", or if the unit's attempt is on or after the `ita_2025` boundary; otherwise ITA1961.
- **P5:** IGST if "IGST" occurs within 60 characters; CUSTOMS if "Customs"; FTP if "Foreign Trade"; otherwise CGST.
- If the resolution is ambiguous, the anchor is recorded but marked `ambiguous`.

**Lookup.** Look up `ref.anchor` to get candidate nodes with weights. Merge by node, summing weights.

**Anchors are NOT shown to the LLM.** They are an independent signal used for bucketing. Showing them would make the LLM agree with them by construction and destroy their value as a check.

### 5.4 Stage 2 — Hierarchical LLM classification

**Step 1: chapter** (task `l3.chapter`, Flash-Lite, temperature 0).

Prompt (`prompts/l3_chapter.v1.md`), abridged:

```
SYSTEM: You map CA Final exam questions to the syllabus of the paper "{paper_name}".
Choose ONLY from the chapter IDs listed. Choose 1 chapter, or 2 if the question
genuinely requires both. If none fits, set none_fits=true. Judge by what the
examiner is testing (the concept or skill the answer applies), not by surface words.

USER:
CHAPTERS (id | name | description):
{shuffled chapter list}

ITEM: {doc_type} {attempt_label} {display_label} — {marks} marks
CONTEXT: {context_text[:3000]}
QUESTION: {question_text[:6000]}
ANSWER (excerpt): {answer_text[:4000]}
```

Output schema: `{"chapters":[{"id":str,"fit":"strong"|"partial"}], "none_fits":bool, "reason":str≤30 words}`.

**Step 2: subtopic** (task `l3.subtopic`, Flash-Lite, temperature 0).

The prompt lists subtopics of the chosen chapter(s) as `id | topic › subtopic | description | keywords` (shuffled).

Output schema:
`{"primary":id|"NONE","secondary":[id]≤2,"justification":str≤30 words,"gist":str≤25 words,"gap":{"parent_topic_id":id,"proposed_name":str}|null}`.

**Gist rules in the prompt:**
- State the concept or task tested, in your own words.
- Don't copy sentences.
- Don't include figures, names or amounts from the question.
- Example: "Lessee accounting for a lease modification reducing scope: remeasure liability, adjust ROU asset, recognise gain."

**Structured output.** Use Gemini's JSON-schema response mode. If the response fails schema validation, retry once with the same prompt. On a second failure: `ops.llm_call.status='schema_error'` and the unit becomes `failed`.

### 5.5 Consistency protocol and buckets

| Run | Model tier | Candidate order | Purpose |
|---|---|---|---|
| R1 | Flash-Lite | original sequence | vote 1 |
| R2 | Flash-Lite | shuffled (seeded by fingerprint) | vote 2 |
| R3 (only if R1.primary ≠ R2.primary) | Flash | shuffled differently | tie-break |

**Anchor consistency.** Let `A` be the set of anchor candidate nodes (non-ambiguous).
- *consistent* if `A` is empty, or primary ∈ `A`, or primary shares a topic with a node in `A`;
- *conflicting* otherwise.

| Bucket | Rule |
|---|---|
| **A** | R1 = R2, and consistent |
| **B** | R1 = R2, and conflicting |
| **C** | R1 ≠ R2, and R3 equals one of them |
| **D** | No majority, or any `NONE` majority, or chapter step `none_fits` |

**Writing suggestions:**
- The winning primary becomes the `primary` suggestion.
- A secondary is included only if it appears in at least 2 runs.
- Losing primaries are kept in `evidence.alternatives`, which the review UI shows as options 1–3.
- The gist comes from the winning run.

A `NONE` majority creates an `ingest.taxonomy_gap` row (with the LLM's `gap` proposal, if any).

### 5.6 Paper 6 (IBS)

- **Step 0 (task `l3.p6_papers`):** choose up to 2 of P1–P5 that the sub-question draws on, plus up to 1 P6-own node (the P6 thin taxonomy fits in the prompt).
- Then run Steps 1–2 within each selected paper.
- Buckets are computed per paper.
- The appearance is published with tags into P1–P5 and P6. L5 applies the P6 cross-paper factor κ (§7.2).

### 5.7 Duplicate detection and propagation

1. Compute MinHash (128 permutations) over word 5-shingles of `normalise(question_text)` for every current gradable unit. Index with LSH (threshold 0.6).
2. Verify candidate pairs with `rapidfuzz.fuzz.token_set_ratio ≥ 85`, and record them in `ingest.duplicate_link`.
3. If a unit's duplicate is already **published**, write a suggestion with `method='duplicate'`, copying the published tags. Bucket A if the duplicate's tags agree with R1/R2, otherwise B. Still reviewed by a human.
4. At publish time, L4 sets `core.appearance.duplicate_of` so the UI can say "also appeared as …".

### 5.8 Execution modes and cost control

| Mode | Command | Use |
|---|---|---|
| Online | `caf classify run --limit 500` | Development, small batches. Concurrency 4. Exponential backoff on 429/5xx (max 5 tries). |
| Batch | `caf classify batch submit` / `caf classify batch collect` | Backfills. Step 1 and Step 2 are separate batch phases because Step 2 depends on Step 1. |
| Shadow | `caf classify run --shadow --band s2017:2019` | Depth Gate: writes `is_shadow=true` suggestions; never enters the review queue |
| Re-run subset | `caf classify run --gap-resolved` / `--paper P3 --since-taxonomy-version 7` | After taxonomy edits |

**Budget.**
- `models.toml` holds prices per model (maintained by hand) and `max_usd_per_run`.
- The ledger (`ops.llm_call`) sums the estimated cost before each call. When the next call would exceed the cap, the run ends with status `aborted_budget`. Units already processed stay processed; the rest remain `pending`. Safe to resume.

```toml
# config/models.toml
[pricing]  # USD per 1M tokens — update from the official pricing page before each backfill
"<flash-lite-model-id>" = { input = 0.10, output = 0.40 }
"<flash-model-id>"      = { input = 0.50, output = 3.00 }

[tasks.l3_chapter]   { model = "<flash-lite-model-id>", temperature = 0.0 }
[tasks.l3_subtopic]  { model = "<flash-lite-model-id>", temperature = 0.0 }
[tasks.l3_tiebreak]  { model = "<flash-model-id>",      temperature = 0.0 }
[tasks.l2_segment]   { model = "<flash-model-id>",      temperature = 0.0 }
[tasks.l2_transcribe]{ model = "<flash-model-id>",      temperature = 0.0 }
[tasks.l0_describe]  { model = "<flash-lite-model-id>", temperature = 0.2 }

[budget]
max_usd_per_run = 5.0
```

Placeholders are deliberate. Fill in the exact model IDs current at the time of the run; `caf llm check` verifies that each configured model responds.

### 5.9 Evaluation (`caf classify eval`)

**Gold data** = curator decisions (`core.decision`) with the suggestion run they were made against.

**Blind sample.** During the first 500 reviews, 10% of items are shown **without** the suggestion first. The curator picks, then the suggestion is revealed. `decision.blind=true`. Precision is computed on blind items to remove anchoring bias; overall figures on all items are reported alongside.

**Metrics** (per paper, per bucket, per method):
- top-1 primary precision;
- chapter-level precision;
- secondary recall;
- NONE rate;
- mean review seconds.

**Gates:**

| Gate | Condition | Action |
|---|---|---|
| Scale-up | Bucket A precision ≥ 95% (blind) | Required before running L3 beyond the first 500 units. Below it: improve descriptors or prompts and re-evaluate. |
| Auto-accept (optional) | Bucket A precision ≥ 97% with n ≥ 200 blind items | `curate.auto_accept_bucket_a` may be set true. The review UI still lists auto-accepted items for spot checks. Default **false** (D3). |

Model changes require running `caf classify eval --replay --model <new>` on the gold set and matching or beating the current model before `models.toml` changes.

### 5.10 L3 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| High D-bucket rate in one chapter | Weak descriptors or missing nodes | Improve descriptors for that chapter. Check `taxonomy_gap`. Reload. Re-run `--paper Px --chapter …`. |
| High B-bucket rate | Anchor map wrong (e.g., section mapped to wrong node) or LLM confusing sibling nodes | Inspect B items. If anchors are wrong, fix `taxonomy/anchors/*`; if the LLM is wrong, sharpen the sibling descriptors to differentiate them. |
| Schema errors > 2% | Model or version change, or a prompt that is too long | Check `ops.llm_call`. Shorten context caps. Confirm the structured-output setting. Re-run failed units. |
| 429 storms | Rate limit (free-tier-like quotas) | Reduce concurrency. Use batch mode. Verify the project is on paid billing (credits). |
| `aborted_budget` | Cap reached | Expected guard. Raise the cap consciously or continue next month. Re-run resumes. |
| Configured model deprecated or unavailable | Provider lifecycle | `caf llm check` fails loudly. Pick the successor. Run the replay eval. Update `models.toml`. |
| Precision drop after taxonomy change | New nodes lack approved descriptors | The loader should have blocked this. Verify descriptor approval and re-run the affected units. |

---

## 6. L4 — Curation & Knowledge Store

### 6.1 Work queues

| Queue | Source | Shown when |
|---|---|---|
| Catalogue | `ingest.document.catalog_status IN ('inferred','needs_curation')` | Always first; it blocks everything downstream |
| Extraction | `extract_status IN ('needs_review','ok_with_warnings')` | Only documents with warnings/errors; `ok` documents skip this |
| Tags | Units with `classify_status='suggested'` and no decision for their fingerprint | Main workload |
| Re-review | Appearances flagged by taxonomy splits, `L1_CONTENT_CHANGED`, or orphaned by reconciliation | Top of the tag queue, marked with the reason |
| Taxonomy gaps | `ingest.taxonomy_gap.status='open'` | Weekly |

### 6.2 Tag review UI (the most-used screen — build it well)

**Layout.**

| Area | Contents |
|---|---|
| Left | Document header (attempt, paper, doc type, series), unit label and marks, full question text, context (for MCQs), answer excerpt (collapsible), and an "open page" button |
| Right | Suggested primary as a breadcrumb path (bucket badge, methods, justification), secondary suggestions, alternatives 1–3, matched anchors, duplicate links, and an editable gist |

**Keyboard map.**

| Key | Action |
|---|---|
| `Enter` / `a` | Accept suggestion as shown |
| `1` `2` `3` | Replace the primary with alternative *n* |
| `/` | Taxonomy search (type-ahead over the paper's nodes) to pick the primary manually |
| `+` | Add a secondary via search |
| `-` | Remove the selected secondary |
| `g` | Edit the gist |
| `n` | None fits → creates or updates a taxonomy gap; the unit stays unpublished |
| `x` | Exclude (not a real question: instructions, errata notes) → `classify_status='excluded'` |
| `k` | Skip (stays in the queue) |
| `u` | Undo the last decision (within the session) |
| `B` | Bulk-accept all remaining **bucket A** items *in this document*, after showing a confirmation list |

**Queue order** within a paper: documents by attempt (newest first); inside each document, units by label. The bucket filter defaults to "all". The session header shows items done, the rate per hour, and the remaining estimate.

**Timing.** `seconds_spent` is measured from item display to decision. It feeds the Depth Gate review-hour estimates.

### 6.3 Publish procedure (per decision)

Each accepted decision is published in one transaction on the `caf_curator` connection:

```
BEGIN;
  INSERT core.decision(...) RETURNING id AS d
  tags ← final tags from payload; shares ← normalise(primary=1.0, secondary=0.5 each)
  law_stale ← compute_law_stale(unit.attempt, paper, tags)            -- §6.5
  UPSERT core.appearance ON CONFLICT (unit_fingerprint) DO UPDATE
      SET gist, marks, display_label, page_start, page_end, law_stale,
          source_unit_id, official_url, status='published', updated_at=now()
  DELETE core.appearance_tag WHERE appearance_id = :id
  INSERT core.appearance_tag (appearance_id, node_id, role, share, decision_id=d) ...
  UPDATE ingest.unit SET classify_status='decided' WHERE fingerprint = :fp AND current
  INSERT core.change_log('appearance', id, 'publish'|'republish', before, after)
COMMIT;
schedule intel recompute (debounced 30 s)
```

- **`official_url`** = the `discovered_link.url` of the unit's document. If several URLs exist, prefer the one on the `resource.cdn.icai.org` host. If there is none (manual import), use the URL from the sidecar or leave it null.
- **Idempotency.** Replaying the same decision yields the same appearance and tags (tested).
- **None fits / exclude** decisions write only `core.decision`. No appearance is created.
- **Undo** writes a new decision with `action='undo'` that restores the previous state: it reads the prior decision's payload, or withdraws the appearance if there was none (`status='withdrawn'`).

### 6.4 Re-parse reconciliation (`caf curate reconcile --doc ID`, run automatically after L2 on published documents)

For each published appearance whose `doc_sha256` equals the document's sha (or that of a superseded predecessor):

1. **Exact:** a current unit with the same fingerprint exists → update `source_unit_id`. Done.
2. **Fuzzy:** a current unit with the same `label_path`, the same marks, and question-text similarity ≥ 0.90 → relink, set the new fingerprint on the appearance, and log to `change_log` (`reason='reparse_relink'`).
3. **Content-changed document** (new sha): match against the new document's units by (2). Matched appearances are relinked **and** queued for re-review if similarity < 0.97.
4. **Otherwise:** `status='orphaned'` and queued in Re-review. **Never deleted automatically.** Orphaned appearances are excluded from scoring until resolved.

### 6.5 Law-staleness

For each appearance, iterate `ref.law_boundary` rows for its paper:
- `policy='exclude'`: the attempt is before the boundary and a tag lies in scope (not exempt) → the appearance is not published at all. The decision is recorded as `exclude` with reason `law_boundary`.
- `policy='mark_stale'`: the attempt is before `first_applicable_attempt` → `law_stale=true`.

Additionally, for P4/P5, appearances older than `depth.toml: stale_after_attempts` (default 6) get `law_stale=true`, since annual Finance Acts amend provisions.

### 6.6 Backups and restore

`caf backup run` (schedule nightly with cron / launchd / Task Scheduler):
1. `pg_dump -Fc -d caf -f data/backups/caf_<ts>.dump`
2. `rsync -a data/blobs/ <backup_target>/blobs/`
3. Copy `taxonomy/`, `overrides/`, `config/` (these are also in git).
4. Rotate: keep 14 daily and 8 weekly dumps.
5. Write `ops.event code=BACKUP_OK` with sizes.

`caf backup verify` (monthly):
1. Restore the latest dump into `caf_verify`.
2. Compare row counts for `app.*` and `core.*` against live.
3. Drop the scratch DB.
4. Alarm on mismatch.

**Restore:**
1. Stop the app.
2. `pg_restore -c -d caf <dump>`.
3. Re-sync the blob store.
4. Run `caf status`, then `caf intel recompute`.

### 6.7 L4 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| Publish transaction fails with FK error on `node_id` | Taxonomy reloaded and the node deprecated or migrated mid-session | Reload the review item. The UI must refresh the taxonomy cache after a `taxonomy_version` change. |
| Many orphans after re-extraction | Profile change altered `label_path` scheme | Stop. Compare the old and new unit lists with `caf curate diff --doc`. If the labels changed systematically, write a one-off relabel mapping (`caf curate relabel --map file.yaml`) instead of re-reviewing everything. |
| Review velocity collapses | Fatigue or too many D/B items | Filter to bucket A for a session and bulk-accept. Fix descriptors for the chapters producing D. The Depth Gate should stop low-value bands. |
| Wrong decision discovered later | Human error | Open the subtopic page → appearance → "Re-review". This creates a queue item. A new decision republishes. Full history is in `core.decision` and `change_log`. |
| Backup older than 48 h alarm | Scheduler not running | Run `caf backup run` manually. Fix the OS scheduler entry. Verify with `caf status`. |

---

## 7. L5 — Intelligence

### 7.1 Inputs and version

- **Inputs:** `core.appearance` (status published) + `core.appearance_tag`, `ref.*`, `app.settings.target_attempt_id` (target `T`), `config/scoring.toml`.
- **Version:** `scoring_version = "v1"`. Any formula change bumps the version, is noted in Plan §13 only if it changes C5's meaning, and is always recorded in `intel.score_run`.

```toml
# config/scoring.toml
version = "v1"
half_life_exam_months = 24
half_life_practice_months = 12
secondary_share = 0.5
p6_cross_paper_factor = 0.5        # κ
law_stale_factor = 0.5             # λ
freq_window_attempts = 5           # N
weak_flag_min_hits = 3
weights = { exam = 0.6, practice = 0.2, prior = 0.2 }
plan = { per_chapter_cap = 3, weak_boost = 0.25, in_progress_boost = 0.10 }
```

### 7.2 Formulas

Notation:
- *a* = appearance
- *s* = subtopic
- `age(a)` = whole months between the exam month of `attempt(a)` and that of *T* (0 if `attempt(a)` is *T*; appearances for attempts after *T* are ignored)
- `share(a,s)` = normalised tag share
- `marks(a)` = appearance marks (0 if null)

**Attributed marks:**

```
m(a,s) = marks(a) · share(a,s) · κ(a,s) · λ(a)
κ(a,s) = p6_cross_paper_factor if source paper is P6 and s is in P1–P5, else 1
λ(a)   = law_stale_factor if a.law_stale else 1
```

**Scores:**

```
decay_e(a) = 2^( −age(a) / H_exam )        decay_p(a) = 2^( −age(a) / H_practice )

E(s) = Σ_{a ∈ exam(s)}     m(a,s) · decay_e(a)
P(s) = Σ_{a ∈ practice(s)} m(a,s) · decay_p(a)
```

**Weightage prior:**

```
section_marks(σ) = ((min_pct + max_pct)/2) / 100 · paper_max
W(s) = section_marks(σ(s)) / |applicable subtopics in σ(s)|
```

**Importance.** Normalise within the paper by the maximum over applicable subtopics (0 if the maximum is 0):

```
Ê = E/maxE,  P̂ = P/maxP,  Ŵ = W/maxW
I(s) = w_exam·Ê + w_practice·P̂ + w_prior·Ŵ
```

**Frequency.** Let `window(p)` = the last N attempts ≤ *T* for which paper *p* has any **published exam** appearance (from `intel.ingestion_coverage`).

```
F(s) = | { attempt ∈ window(p) : ∃ exam appearance of that attempt tagged s } |
freq_window = |window(p)|    (may be < N early on — the UI shows "F of freq_window")
```

**Weak-coverage flag** (per user, computed at request time):

```
weak(s) = applicable(s,T) ∧ F(s) ≥ weak_flag_min_hits ∧ freq_window ≥ N ∧ status(s) = not_started
```

The `freq_window ≥ N` guard prevents flags from firing on thin data.

**Coverage** (per user):

```
cov(paper)   = Σ_{s done, applicable} W(s) / Σ_{s applicable} W(s)
cov(group)   = same sums over the group's papers
cov(overall) = same sums over all current papers
in_progress share is reported separately, never blended in.
```

**Why payload** (`GET /why/subtopic/{id}`): the list of contributing appearances with `m(a,s)`, decay and contribution, plus W and its section. Every dashboard number must be reproducible from this payload.

### 7.3 Recompute (`caf intel recompute [--shadow --include-bands …]`)

1. Insert an `intel.score_run` (status `running`).
2. Compute all rows in Python over SQL-fetched data. At expected sizes (≤ 50k appearances, ≤ 5k subtopics) this takes seconds.
3. Bulk insert `intel.subtopic_score` and `intel.ingestion_coverage`.
4. In one transaction: set the old current run `is_current=false` and the new one `is_current=true`, `status='ok'`.
5. Keep the last 10 runs, delete older ones (cascade).

A failure leaves the previous run current (`status='failed'` on the new run, event `L5_RECOMPUTE_FAILED`). The UI keeps working.

**Triggers:**
- a debounced call after publishes;
- after `caf taxonomy load --apply`;
- after the target attempt changes in settings;
- manual.

### 7.4 Next-week plan (request-time)

```
budget_items = floor(hours_per_week · 60 / minutes_per_subtopic)
cands = applicable subtopics with status ∈ {not_started, in_progress}
score(s) = I(s) + weak_boost·[weak(s)] + in_progress_boost·[status=in_progress]
sort cands by score desc
pick greedily, skipping s if its chapter already has per_chapter_cap picks, until budget_items
reason(s) = template from facts: "Asked in {F} of last {freq_window} exams ({exam_marks_total} marks); weightage section {σ}: {min}-{max}%"
```

Optional filters: paper or group (e.g., studying Group 2 only).

### 7.5 Revision queue (request-time)

```
for s with status=done:
   k   = number of revision_events for s since first_done_at
   due = (last_revised_at or first_done_at) + intervals[min(k, len-1)] days
   'shaky' outcome resets k to 0 for that subtopic
due_list = s with due ≤ today, ordered by I(s) desc, then overdue days desc
```

### 7.6 Depth Gate computation (`caf depth gate --paper P2 --band s2017:2019`)

**Preconditions:** the band's documents are acquired, confirmed, extracted, and shadow-classified (`caf classify run --shadow --band …`).

1. **Baseline** = the current score run.
2. **Shadow run** = recompute with the band's shadow suggestions included. Only bucket A/B primaries count, as provisional appearances with `share=1`.
3. **Metrics per paper:**
   - `K = 50`;
   - `jaccard = |top_K(base) ∩ top_K(shadow)| / |top_K(base) ∪ top_K(shadow)|`;
   - `spearman` over the union of the two top-K sets;
   - `newly_asked_nodes` = subtopics with no exam history in the baseline and some in the shadow;
   - `units_to_review` = gradable units in the band;
   - `est_review_hours = units_to_review × median(seconds_spent over the last 500 decisions) / 3600`.
4. **Recommendation:**
   - `continue` if `jaccard < 0.9` or `newly_asked_nodes ≥ 10`;
   - else `continue_practice_value` if the paper is flagged `practice_value = true` in `depth.toml`;
   - else `stop`.
5. Write `intel.depth_gate_report`. **The curator records the final decision** in `config/depth.toml`.

```toml
# config/depth.toml
[paper.P1] practice_value = true   ; bands_open = ["s2023:*", "s2017:2023", "s2017:2022"]
[paper.P2] practice_value = true   ; bands_open = ["s2023:*"]
[paper.P4] practice_value = false  ; stale_after_attempts = 6
[paper.P5] practice_value = false  ; stale_after_attempts = 6
```

### 7.7 L5 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| Dashboard shows old numbers | Recompute failed; previous run still current | `caf status` shows `L5_RECOMPUTE_FAILED` with the traceback. Fix and re-run. |
| Importance dominated by one ancient appearance | Half-life too long, or law_stale not applied | Check the why payload. Adjust `scoring.toml` (bump version) or fix the law boundaries. |
| Weak flags never appear | Fewer than N exam attempts ingested for the paper | Expected. The UI shows "needs ≥ N ingested exams". Ingest more attempts. |
| Coverage over 100% or NaN | Deprecated node still counted, or zero-weight section | Contract test should catch this. Verify applicability, then weightage membership. |
| Depth Gate says continue forever | Shadow tags noisy (many B), or K too small | Inspect B-heavy chapters. Consider K = 100 for papers with more than 500 subtopics. |

---

## 8. L6 — Serving

### 8.1 Process model

- `caf serve` runs `uvicorn api.main:app --host 127.0.0.1 --port 8765`.
- The FastAPI app mounts `/api/v1` routers and serves `web/dist` as static files, with an SPA fallback (non-API GETs return `index.html`).
- **Two SQLAlchemy engines:** `app_engine` (role `caf_app`) and `curator_engine` (role `caf_curator`). Routers under `/api/v1/curate` depend on `curator_engine`; all others on `app_engine`. The single user is resolved by a dependency returning `user_id=1`. This is the only place to change when auth is added.
- **Errors:** RFC 7807 `application/problem+json` with a stable `type` code (e.g., `/errors/taxonomy-node-not-found`).
- **Remote access** (e.g., from a phone): install Tailscale on both devices and access the app via its tailnet address. Do not bind `0.0.0.0` on an untrusted network, and do not open router ports.

### 8.2 Student API (role `caf_app`)

| Method & path | Returns / accepts | Notes |
|---|---|---|
| `GET /meta` | versions (taxonomy, scoring, API), target attempt, current score run time, ingestion coverage per paper×attempt | UI banner "data as of…" |
| `GET /papers` | papers with coverage, done/in-progress counts | |
| `GET /tree?paper=P1` | nested chapter → topic → subtopic with status, `importance` (0–1), `F/freq_window`, `weak`, `applicable` | One call per paper; cached by TanStack Query |
| `GET /subtopics/{id}` | path, descriptor, status and timestamps, note, scores, **appearances[]**: `{id, attempt_label, doc_type, signal_class, series, label, marks, gist, law_stale, duplicate_of_label?, source_href}` | **No question/answer text** (D2) |
| `PUT /subtopics/{id}/progress` | `{status}` → progress + event | Idempotent. Writes `app.progress_event`. Sets `first_done_at` on first done. |
| `PUT /subtopics/{id}/note` | `{body ≤ 5000 chars}` | |
| `POST /subtopics/{id}/revisions` | `{outcome: ok\|shaky}` | Updates `last_revised_at` |
| `GET /dashboard` | coverage (overall / group / paper), last-7-days completions (daily series from `progress_event`), weak list (top 10), plan preview (top 5), revision due count, ingestion coverage | Single payload for the home screen |
| `GET /plan` | full next-week plan with reasons | |
| `GET /revision/due` | due list | |
| `GET/POST/DELETE /mock-tests` | mock-test log CRUD | Trend per paper computed in the UI |
| `GET/POST /sessions` | optional study-session logging | |
| `GET /search?q=` | results across nodes and descriptors, gists (via appearance → subtopic), notes | Postgres `websearch_to_tsquery` |
| `GET/PUT /settings` | target attempt, exam date, hours per week, minutes per subtopic | Changing the target triggers a recompute |
| `GET /why/subtopic/{id}` | contribution breakdown (§7.2) | |
| `GET /appearances/{id}/source` | 302 to `official_url#page=N`; if the URL is marked dead or null → 302 to `/local/{sha}#page=N` | |
| `GET /local/{sha}` | streams the local PDF | Only when the request comes from localhost or tailnet (checked); never a public route |

### 8.3 Curator API (role `caf_curator`, prefix `/curate`)

| Method & path | Purpose |
|---|---|
| `GET /catalog?status=` · `PATCH /documents/{id}` · `POST /documents/confirm {ids}` · `POST /documents/{id}/reject` | Catalogue review |
| `GET /documents/{id}/page/{n}.png` | Page thumbnail render |
| `GET /extraction?status=` · `GET /documents/{id}/debug` · `POST /documents/{id}/re-extract` | Extraction review (`re-extract` only sets `extract_status='pending'`; the CLI runs L2 — the live plane never runs pipeline stages) |
| `GET /review/queue?paper=&bucket=&reason=` | Next N items (default 20, prefetch) |
| `GET /review/units/{unit_id}` | Full item (full text allowed here) |
| `POST /review/units/{unit_id}/decision` | `{action, primary?, secondary?, gist?, seconds_spent, blind}` → publishes (§6.3) |
| `POST /review/documents/{doc_id}/bulk-accept?bucket=A` | Returns a preview list unless `confirm=true` |
| `POST /review/undo` | Undo the last decision in this session |
| `GET /gaps` · `PATCH /gaps/{id}` | Taxonomy gaps |
| `GET /status` | Stage counts, alarms, recent runs, LLM spend this month, backup age |
| `POST /intel/recompute` | Manual trigger |

### 8.4 Frontend

**Routes.**

| Path | View |
|---|---|
| `/` | Dashboard |
| `/p/:paper` | Paper tree |
| `/s/:subtopicId` | Subtopic page |
| `/plan` | Next-week plan |
| `/revision` | Revision queue |
| `/mocks` | Mock-test log |
| `/search` | Search |
| `/settings` | Settings |
| `/curate/catalog`, `/curate/extraction`, `/curate/review`, `/curate/gaps`, `/curate/status` | Curator area |

**Subtopic page** (the core UX, System Design §5.3):

1. **Header:** path breadcrumb, status toggle (three-state segmented control), applicability badge.
2. **"Exam history" panel** (exam appearances, newest first):
   - `Sept 2025 · Q3(b) · 8 marks — {gist}  [Open page ↗]`;
   - `law_stale` badge where applicable;
   - "also appeared as …" chips for duplicates;
   - a mini-strip of the last N ingested attempts with hit/miss dots.
3. **"ICAI practice" panel** (RTP/MTP) — the same layout, visually secondary.
4. **Importance explanation** (collapsible) from `/why`.
5. **Notes** — autosaved with 1 s debounce.

**Data layer.**
- A typed client is generated from OpenAPI (`pnpm gen:api` → `web/src/api/schema.d.ts`) and used with `openapi-fetch`. No hand-written fetch calls.
- TanStack Query with key conventions `['tree', paper]`, `['subtopic', id]`, `['dashboard']`.
- Progress mutations are **optimistic**: update the tree and subtopic caches, then roll back on error with a toast. On success, invalidate `dashboard`, `plan` and `revision`.

**Curator review screen.**
- Keyboard handler per §6.2, with focus management so shortcuts never fire inside text inputs.
- Prefetch the next 5 items.
- Decisions POST in the background, with a visible retry state. Items stay in a local pending list until the server confirms. A failed POST keeps the item and shows an error. **Never drop a decision silently.**

**Styling.** Visual design is not in scope of this Guide beyond these requirements: responsive (usable on a phone over the tailnet), light/dark themes, and accessible contrast.

### 8.5 Contract enforcement for C6

- `caf api export-openapi > web/openapi.json` is committed.
- CI (or a pre-commit hook) fails if the export differs from the committed file, or if the generated TS types differ.
- **Breaking changes** (removing or renaming fields, changing types) require `/api/v2`, with v1 kept until the frontend migrates. For a single-developer project, "keep until migrated" can be the same PR, but the version bump is still made so the rule stays mechanical.

### 8.6 L6 failure runbook

| Symptom | Likely cause | Action |
|---|---|---|
| App starts, pages empty | DB not running or roles/grants missing | `docker compose up -d db`; `caf db grants`; `caf status` |
| Student endpoint 500 with a permission error | A student route used the curator engine or vice versa | This is the role separation working. Fix the dependency wiring. Add a test. |
| "Open page" goes to an ICAI 404 | File moved or removed | Mark it dead (automatic via the weekly `caf acquire linkcheck`). The source redirect falls back to the local copy. |
| Progress toggle reverts | Optimistic update rolled back after an API error | Check the toast and API logs. `progress_event` shows whether the write landed. |
| TS build fails after a backend change | OpenAPI drift | Run `pnpm gen:api`. If the change was breaking, you needed `/api/v2`. |
| Dashboard numbers disagree with the why payload | Stale score run or caching | Check `/meta` score-run time, then `caf intel recompute`. Query caches invalidate on focus. |

---

## 9. CLI reference (`caf`)

| Command | Layer | Effect |
|---|---|---|
| `caf db up` / `caf db migrate` / `caf db grants` | infra | Start Postgres, apply Alembic migrations, (re)apply role grants |
| `caf status [--json]` | all | Per-stage counts, alarms, last runs, LLM spend (month), backup age |
| `caf taxonomy bootstrap --paper Px [--diff-only] [--heading-mode toc\|size]` | L0 | Draft/refresh the tree YAML from study material |
| `caf taxonomy describe --paper Px` | L0 | Draft descriptors (`approved:false`) |
| `caf taxonomy guidelines-draft --doc ID` | L0 | Propose applicability rules from a Study Guidelines PDF |
| `caf taxonomy load [--apply]` | L0/L4 | Validate → diff → plan → apply (+ migration handlers, recompute) |
| `caf acquire discover [--source ID]` | L1 | Walk seeds, record links |
| `caf acquire fetch [--limit N] [--attempt …] [--doc-type …]` | L1 | Download pending links |
| `caf acquire assist --source ID \| --url URL` / `assist-download` | L1 | Human-driven discovery and download |
| `caf acquire import DIR [--interactive]` | L1 | Manual import |
| `caf acquire catalog --tui` | L1/L4 | Terminal catalogue review (alternative to the web UI) |
| `caf acquire linkcheck` | L1 | HEAD-check official URLs of published documents weekly; mark dead ones |
| `caf extract run [--doc ID] [--profile ID] [--status …]` | L2 | Extract |
| `caf extract debug --doc ID` | L2 | Write debug HTML/PNGs |
| `caf extract report --profile ID` | L2 | Validation summary |
| `caf classify run [--limit N] [--paper Px] [--shadow --band B]` | L3 | Online classification |
| `caf classify batch submit\|collect` | L3 | Batch-API backfill |
| `caf classify eval [--replay --model M]` | L3 | Precision metrics / model comparison |
| `caf llm check` | L3 | Verify configured models respond; print deprecation warnings from config |
| `caf curate reconcile --doc ID` · `caf curate diff --doc ID` · `caf curate relabel --map F` | L4 | Reconciliation tools |
| `caf intel recompute [--shadow …]` | L5 | Score run |
| `caf depth gate --paper Px --band B` | L5 | Depth Gate report |
| `caf serve [--dev]` | L6 | Run the app (`--dev` proxies to the Vite dev server) |
| `caf api export-openapi` | L6 | Write the OpenAPI JSON |
| `caf backup run\|verify` | ops | Backups |

Every data-writing command opens an `ops.run`, is **idempotent**, and is safe to interrupt with Ctrl-C. On interrupt the run is closed as `partial`, and items in `running` state are reset to their prior state on the next start (stale `running` older than 30 min → reset).

---

## 10. Testing strategy (detail)

| Suite | What | Data | Runs |
|---|---|---|---|
| `unit` | Pure functions: inference regexes, normalisers, validators, V3 attemptable max, anchor parsing and act resolution, fingerprints, scoring formulas, plan/revision algorithms | Synthetic | Every commit |
| `contracts` | Invariants of C0–C6 against a migrated test DB seeded with a mini taxonomy (2 papers × 2 chapters) | Synthetic seed | Every commit |
| `db` | Alembic upgrade/downgrade round-trip; role grants (the `caf_app` role **cannot** insert into `core`) | Empty DB | Every commit |
| `extraction_golden` | Profile outputs versus hand-written expected YAML | Private fixture PDFs (3+ per profile) | Every commit (skipped if fixtures are absent) |
| `llm_contract` | Prompt builders produce the expected structure; response parsing against **recorded** responses (`tests/fixtures/llm/*.json`) | Recorded | Every commit — **no live LLM calls in tests** |
| `publish` | Publish idempotency, undo, reconciliation (exact, fuzzy, orphan), taxonomy split/merge handlers | Synthetic | Every commit |
| `api` | httpx TestClient over both routers; D2 check: student responses contain no `question_text`/`answer_text` keys (schema-level assertion) | Seed | Every commit |
| `openapi_drift` | Exported OpenAPI equals the committed file; generated TS equals the committed file | — | Every commit |
| `e2e` | Playwright: mark done → dashboard coverage changes; review accept → subtopic history shows the appearance | Seed + small fixture | Before merging to main |
| `eval` (manual) | `caf classify eval` on real decisions | Real | After prompt, model or descriptor changes |

**Fixture policy.** Fixture PDFs are ICAI material. They live in `tests/fixtures/pdfs/`, which is git-ignored or in a private repository only. Tests that need them are skipped when they are absent, so CI never requires them.

---

## 11. Operational runbooks

### 11.1 First-time setup (M0)

1. Install Docker, Python 3.12 + `uv`, Node LTS + `pnpm`, Tesseract, and `ocrmypdf`.
2. `cp .env.example .env`. Set the DB passwords and `GEMINI_API_KEY`. The key must come from a Google Cloud project **with billing enabled** (the AI Pro Developer Program credits apply there) — not a free-tier key (Plan §6.3).
3. Run `caf db up && caf db migrate && caf db grants`, then `uv run playwright install chromium`.
4. `caf llm check`.
5. Fill `taxonomy/registry/*.yaml` and verify each entry against ICAI announcements (set `verified: true`).

### 11.2 A new attempt's material is released

1. Add the attempt to `attempts.yaml` if it is missing. Run `caf taxonomy load --apply`.
2. Add or update seed URLs if ICAI created new pages. Then `caf acquire discover && caf acquire fetch`.
3. Catalogue review: confirm the new documents.
4. `caf extract run --status pending`. Review `needs_review` documents.
5. `caf classify run` (or batch). Review the tags.
6. For Study Guidelines of the new attempt: `caf taxonomy guidelines-draft`, then curate `applicability/<attempt>.yaml` and `load --apply`.
7. Set `settings.target_attempt_id` if you are now targeting it. This triggers a recompute.

### 11.3 ICAI revises the syllabus or study material

1. Acquire the new study material.
2. `caf taxonomy bootstrap --paper Px --diff-only`, then edit the YAML with explicit migrations for split/merge/deprecate.
3. `caf taxonomy describe` for new nodes, then approve them.
4. `caf taxonomy load` (read the plan carefully), then `--apply`.
5. Work the Re-review queue (tags flagged by splits).
6. Check the progress `verify_flag` items on the dashboard.

### 11.4 Gemini model deprecation notice

1. Pick the successor model ID. Add its price to `models.toml [pricing]`.
2. `caf classify eval --replay --model <new>` on the gold set.
3. If it matches or beats the current model, update `models.toml` tasks and commit. Otherwise try the next candidate.
4. Existing suggestions and decisions are unaffected (the model ID is recorded per run).

### 11.5 Monthly hygiene

- `caf backup verify`.
- `caf acquire discover && fetch` (catches silent additions).
- `caf acquire linkcheck`.
- `caf classify eval` (drift watch).
- Review open taxonomy gaps.
- Check LLM spend in `caf status`.

---

## 12. Global failure-handling principles

These apply to every layer and override convenience:

1. **Fail closed toward the student.** When unsure, don't publish. A missing history entry is a gap; a wrong one is misinformation.
2. **Never lose human input.** Curator decisions and progress are the only irreplaceable data. They are keyed by stable IDs and fingerprints (not row IDs), are never overwritten by automated stages, and are backed up nightly.
3. **Every failure is a row, not just a log line.** Item-level failures live in status columns (`link_status`, `extract_status`, `classify_status`) plus `ops.event`. `caf status` must be able to answer "what is stuck and why" without reading logs.
4. **Re-running is the universal fix.** Every stage is idempotent and selects its own pending work. After fixing a cause, re-run the stage — never hand-edit staging rows. Hand fixes go through overrides, YAML or curator actions.
5. **No silent semantic fallbacks.** A fallback that changes meaning (LLM segmentation, OCR transcription, fuzzy relinking) must lower confidence, set a flag, and route to review.
6. **Stop the line on systemic signals.** Alarms (`L1_ZERO_LINKS`, `L1_HUMAN_CHECK`, extraction failure rate > 20%, bucket-A precision below the gate, budget cap, stale backup) pause the affected stage for the run. They don't let it grind through thousands of bad items.
7. **Respect the source.** Robots rules, human checks and rate limits are hard constraints. The answer to "blocked" is always assisted or manual mode, never a workaround.
8. **Change the contract, not the workaround.** If a layer needs data its input contract doesn't provide, amend the contract in the Plan (§4) instead of reaching across layers.

---

## 13. Definition-of-Done checklists

**L0**
- [ ] Registries filled and verified.
- [ ] 6 papers loaded.
- [ ] Granularity report reviewed.
- [ ] All active subtopic descriptors approved.
- [ ] Anchor maps for P1/P3/P4 (both acts)/P5 loaded.
- [ ] Weightages loaded.
- [ ] Applicability for the target attempt loaded.
- [ ] Loader validation clean.

**L1**
- [ ] All current-scheme exam and practice documents catalogued and confirmed.
- [ ] Zero `new` links.
- [ ] Every failure is `manual_required` with a reason, or resolved.
- [ ] Re-run fetches nothing.
- [ ] Assisted and manual paths tested once.

**L2**
- [ ] Per-profile golden tests pass.
- [ ] Unseen-sample DoD met (boundaries ≥ 99%, marks 100%, pairing ≥ 98%).
- [ ] No in-scope document left in `pending`/`failed`.

**L3**
- [ ] Blind-sample bucket A precision ≥ 95%.
- [ ] NONE rate < 3%.
- [ ] Budget ledger accurate against Google billing (± 10%).
- [ ] `caf llm check` green.

**L4**
- [ ] Publish/undo/reconcile tests pass.
- [ ] Review velocity measured.
- [ ] Backups and restore verified.
- [ ] No orphaned appearances older than 7 days.

**L5**
- [ ] Formula tests pass.
- [ ] The why payload reproduces dashboard numbers.
- [ ] Ingestion coverage shown.
- [ ] Depth Gate report produced for at least one band.

**L6**
- [ ] All routes functional on real data.
- [ ] D2 assertion test passes.
- [ ] OpenAPI drift check in place.
- [ ] e2e smoke passes.
- [ ] Remote access (if used) via tailnet only.

---
*End of document.*
