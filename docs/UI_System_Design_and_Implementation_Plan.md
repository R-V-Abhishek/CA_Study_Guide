# CA Final Study Companion — UI System Design & Implementation Plan

> **Version**: 1.0 | **Audience**: Frontend engineers, product designers  
> **Backend**: FastAPI + PostgreSQL (already built, L0–L5 complete)  
> **Target**: Two UIs — (1) Student Study App, (2) Curator Annotation Tool

---

## 1. Technology Recommendation

### Framework: **Next.js 14 (App Router) + TypeScript**

| Requirement | Why Next.js wins |
|---|---|
| SSR for fast first paint of study dashboard | Built-in App Router with React Server Components |
| Static taxonomy tree (changes rarely) | ISR (Incremental Static Regeneration) caches it at edge |
| Real-time annotation queue updates | Server-Sent Events or SWR polling — works natively |
| FastAPI co-deployment | Next.js API routes proxy to FastAPI; single domain |
| Mobile responsiveness | Tailwind CSS utility classes + Radix UI primitives |
| Type safety against backend contracts | OpenAPI → `openapi-typescript` auto-generates types |
| Rich data tables (curator queue) | TanStack Table v8 (headless, fast, fully typed) |

### Full Stack Choices

```
Frontend:   Next.js 14 (App Router) + TypeScript
Styling:    Tailwind CSS 3 + shadcn/ui (Radix UI + Tailwind)
State:      Zustand (lightweight, no boilerplate) + TanStack Query (server cache)
Charts:     Recharts (lightweight, composable, accessible)
Tables:     TanStack Table v8
Forms:      React Hook Form + Zod
Icons:      Lucide React
Fonts:      Inter (variable) — ICAI-friendly, legible in dense tables
Animation:  Framer Motion (page transitions, skeleton loaders)
API types:  openapi-typescript (auto-generated from FastAPI /openapi.json)
```

### Why not React Native / Expo?
The student app needs deep-linking to subtopics, printable study plans, and keyboard shortcuts for power users. A responsive web app with PWA manifest covers mobile and desktop with one codebase.

---

## 2. Project Structure

```
web/
├── apps/
│   ├── student/          # Student Study App (public-facing)
│   └── curator/          # Annotation & Curation Tool (internal)
├── packages/
│   ├── ui/               # Shared shadcn/ui component library
│   ├── api-client/       # Generated TypeScript types + fetch wrappers
│   └── config/           # Shared Tailwind config, ESLint, TypeScript
├── package.json          # Turborepo workspaces
└── turbo.json
```

Both apps are separate Next.js apps in a Turborepo monorepo, sharing the `ui` and `api-client` packages.

---

## 3. Student Study App (`apps/student`)

### 3.1 Information Architecture

```
/ (Dashboard)
├── /papers                         Papers overview list
├── /papers/[paperId]               Paper detail: tree + importance heat-map
│   └── /papers/[paperId]/[nodeId]  Subtopic detail + why + appearances
├── /plan                           Weekly study plan (ranked by importance)
├── /revision                       Spaced revision queue (due today)
├── /progress                       Coverage tracker across all papers
└── /mock                           Mock test history + performance
```

### 3.2 Dashboard (`/`)

**Purpose**: The student's home screen. Answers: "What should I study today?"

**Layout**: 3-column grid (collapses to 1 on mobile)

```
┌─────────────────────────────────────────────────────────────────┐
│  Good morning, [Name]. Exam in 47 days.  [P-Nov 2025]           │
│  ─────────────────────────────────────────────────────          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐ │
│  │  STUDY TODAY   │  │   COVERAGE     │  │  REVISION DUE      │ │
│  │                │  │                │  │                    │ │
│  │ 1. Ind AS 115  │  │  P1 ████░░ 60% │  │  3 topics due      │ │
│  │ 2. SA 700      │  │  P2 ██████ 82% │  │  today             │ │
│  │ 3. Sec 115JB   │  │  P3 ███░░░ 42% │  │                    │ │
│  │  [Full Plan →] │  │  P4 ████░░ 55% │  │ [Open Queue →]     │ │
│  └────────────────┘  └────────────────┘  └────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  IMPORTANCE LEADERS  (Top 5 untouched high-value topics)   │  │
│  │                                                            │  │
│  │  #1  Ind AS 115 — Rev Recognition  I=0.92  P1  [Study →]  │  │
│  │  #2  Companies Act — Merger Scheme I=0.88  P2  [Study →]  │  │
│  │  #3  Tax Audit — Sec 44AB          I=0.85  P4  [Study →]  │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Data contracts**:
- `GET /api/v1/dashboard` → `DashboardResponse`
- `GET /api/v1/plan?papers=P1,P2,P3,P4,P5,P6&hours=2` → `StudyPlanResponse`
- `GET /api/v1/revision/due` → `RevisionDueResponse`

**UX priorities**:
- Dashboard loads < 200ms via RSC + cached plan
- "Study Today" list is the first visible element above the fold
- Coverage bars animate in from 0% on first load (Framer Motion)
- Importance score rendered as a pill: `●●●○○` dots + percentage

---

### 3.3 Papers Overview (`/papers`)

**Purpose**: Entry point into each of the 6 papers. Shows importance ranking.

**Layout**: Card grid, 2 columns on desktop, 1 on mobile

```
┌──────────────────────────────────────────────────────┐
│  Papers                         [Filter: All Groups ▼]│
│                                                        │
│  ┌────────────────────┐  ┌────────────────────────┐   │
│  │ P1 · Financial     │  │ P2 · Corporate &       │   │
│  │ Reporting          │  │ Other Laws             │   │
│  │                    │  │                        │   │
│  │ Coverage  ██░░ 60% │  │ Coverage  ████ 82%     │   │
│  │ Avg Imp   ●●●●○    │  │ Avg Imp   ●●●○○        │   │
│  │ 39 subtopics       │  │ 41 subtopics           │   │
│  │ 8 due for revision │  │ 2 due for revision     │   │
│  │                    │  │                        │   │
│  │ [Open Paper →]     │  │ [Open Paper →]         │   │
│  └────────────────────┘  └────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**Data contracts**:
- `GET /api/v1/papers` → `Paper[]` with `coverage_pct`, `avg_importance`

---

### 3.4 Paper Detail (`/papers/[paperId]`)

**Purpose**: The core study screen. Shows the syllabus tree with importance scores and progress.

**Layout**: Two-pane (sidebar tree + main content)

```
┌──────────────────────────────────────────────────────────────────┐
│ ← Papers   P1: Financial Reporting            [Progress: 60%]     │
├────────────────────────┬─────────────────────────────────────────┤
│ SYLLABUS TREE          │  SELECTED: Ind AS 115                   │
│                        │  ─────────────────────────────────────  │
│ Chapter 1: Ind AS      │  Importance: ●●●●● 0.92                 │
│  > Ind AS 115  ●●●●●  │  Frequency:  Asked 6× (2018–2024)       │
│    Ind AS 116  ●●●○○  │  Weightage:  12–16 marks typically       │
│  > Ind AS 103  ●●●●○  │  Law Status: ✓ Current law              │
│                        │                                          │
│ Chapter 2: Companies   │  [Why is this important? ▼]             │
│  > Sec 149     ●●●●○  │   E(s)=0.91 from 6 exam appearances     │
│  > Sec 168     ●●●○○  │   W(s)=0.78 high section weightage      │
│                        │   P(s)=0.62 appears in 3 RTPs           │
│ Chapter 3: Audit       │                                          │
│  > SA 700      ●●●●○  │  STATUS                                  │
│  > SA 240      ●●○○○  │  ┌──────────────────────────────────┐   │
│                        │  │ ○ Not Started  ● In Progress     │   │
│ [Filter: Not Done ▼]   │  │ ✓ Done  [Mark as Done]           │   │
│                        │  └──────────────────────────────────┘   │
│                        │                                          │
│                        │  PAST APPEARANCES (3 of 6)              │
│                        │  Nov 2024 · 16 marks                    │
│                        │  May 2023 · 12 marks                    │
│                        │  Nov 2022 · 16 marks                    │
│                        │  [Show all 6 →]                         │
└────────────────────────┴─────────────────────────────────────────┘
```

**UX details**:
- Tree nodes sorted by `importance DESC` by default; toggle to sort by `seq` (syllabus order)
- Colour-coded importance: `●●●●●` = red (critical), `●●●○○` = amber, `●●○○○` = grey
- Progress badge (Done/In Progress/Not Started) visible inline in tree
- Clicking a node loads its detail instantly via optimistic RSC prefetch (hover = prefetch)
- "Why is this important?" expands an inline breakdown showing E(s), P(s), W(s) contributions
- Past appearances show date, marks, and law_stale badge if applicable
- On mobile: tree becomes a bottom drawer

**Data contracts**:
```typescript
GET /api/v1/papers/{paperId}/tree
→ PaperTreeResponse {
    paper: Paper
    chapters: ChapterNode[] {
      id, name, seq
      topics: TopicNode[] {
        id, name, seq, importance, progress_status
        subtopics: SubtopicNode[] {
          id, name, seq, importance, freq_hits, weight_prior
          progress_status, law_stale
        }
      }
    }
  }

GET /api/v1/subtopics/{nodeId}
→ SubtopicDetailResponse {
    node: SubtopicNode
    score: SubtopicScore { exam_score, practice_score, weight_prior, importance }
    why: WhyResponse { explanation, drivers }
    appearances: AppearanceSummary[] { attempt_id, marks, law_stale, display_label }
    progress: ProgressState { status, first_done_at, last_revised_at }
  }

PUT /api/v1/subtopics/{nodeId}/progress
body: { status: "not_started" | "in_progress" | "done" }
→ ProgressState
```

---

### 3.5 Study Plan (`/plan`)

**Purpose**: AI-generated weekly plan showing exactly what to study and in what order.

**Layout**: Timeline-style day-by-day cards

```
┌───────────────────────────────────────────────────────────────────┐
│ Study Plan   [Today] [This Week] [Next 2 Weeks]                   │
│ Available hours: [2 hrs/day ▼]   Papers: [All ▼]                  │
│                                                                     │
│ MONDAY · Sep 30                                                     │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │ 1. Ind AS 115 — Revenue Recognition        45 min  ●●●●●    │   │
│ │    P1  · Not Started · 12–16 marks typical                  │   │
│ │    [Start →]                                                 │   │
│ │ ─────────────────────────────────────────────────────────── │   │
│ │ 2. SA 700 — Auditor's Report               30 min  ●●●●○    │   │
│ │    P3  · In Progress · 8–12 marks                           │   │
│ │    [Continue →]                                              │   │
│ └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│ TUESDAY · Oct 1                                                     │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │ 1. CARO 2020                               30 min  ●●●●○    │   │
│ └──────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

**Data contract**:
```typescript
GET /api/v1/plan?hours=2&days=7&papers=P1,P2,P3
→ StudyPlanResponse {
    generated_at: string
    per_day_minutes: number
    days: DayPlan[] {
      date: string
      items: PlanItem[] {
        node_id, node_name, paper_code
        estimated_minutes, importance, progress_status
      }
    }
  }
```

**UX details**:
- Plan regenerates on hours/filter change with optimistic UI (skeleton replaces items while loading)
- Progress badges update in real-time when the student marks items done
- Completed items stay visible with a strikethrough + checkmark for context

---

### 3.6 Revision Queue (`/revision`)

**Purpose**: Spaced repetition interface. Shows what's due today.

```
┌──────────────────────────────────────────────────────────────────┐
│ Revision Queue                              Today: 5 due          │
│                                                                    │
│ ┌────────────────────────────────────────────────────────────┐    │
│ │ 1. Ind AS 116 — Leases                        P1  Due today│    │
│ │    Last revised: 21 days ago · Interval 3: 21 days         │    │
│ │                                                            │    │
│ │    After revision:  [✓ Got it]  [≈ Shaky — reset]         │    │
│ └────────────────────────────────────────────────────────────┘    │
│                                                                    │
│ ┌────────────────────────────────────────────────────────────┐    │
│ │ 2. Companies Act — Section 149                P2  Due today│    │
│ └────────────────────────────────────────────────────────────┘    │
│                                                                    │
│  Upcoming (next 7 days): 12 topics                                 │
└──────────────────────────────────────────────────────────────────┘
```

**Data contracts**:
```typescript
GET /api/v1/revision/due
→ RevisionDueResponse {
    due_today: RevisionItem[] { node_id, node_name, paper_code, due_date, interval_days }
    upcoming_7d: number
  }

POST /api/v1/revision/{nodeId}/outcome
body: { outcome: "ok" | "shaky" }
→ { next_due_date: string, next_interval_days: number }
```

---

### 3.7 Performance & Loading Strategy

| Route | Strategy | Cache TTL |
|---|---|---|
| `/` Dashboard | RSC + SWR revalidate | 60s |
| `/papers` | ISR | 5 min |
| `/papers/[id]/tree` | ISR + client-side progress overlay | 5 min |
| `/plan` | Dynamic (depends on hours/filters) | No cache |
| `/revision` | Dynamic (due dates change daily) | No cache |
| Subtopic detail | React Query with optimistic updates | 30s |

**First Contentful Paint target**: < 1.0s on 4G  
**Time to Interactive**: < 2.0s on 4G  
**Approach**: 
- Server Components for static structure (papers list, tree skeleton)
- Client Components only for interactive elements (progress toggle, plan filters)
- Suspense boundaries with skeleton loaders (never blank screens)
- `prefetch` on hover for subtopic detail panels

---

## 4. Curator Annotation Tool (`apps/curator`)

This is the internal tool for human review of classification suggestions — the "human in the loop" for the L3 → L4 pipeline.

### 4.1 Information Architecture

```
/ (Queue Dashboard)
├── /queue                    Curation review queue (main workbench)
│   └── /queue/[unitId]       Single-unit decision panel
├── /bulk                     Bulk accept Bucket A view
├── /documents                Document catalog and re-ingestion
│   └── /documents/[docId]    Document detail + unit list
├── /taxonomy                 Browse/edit taxonomy descriptors
│   └── /taxonomy/[nodeId]    Node editor (keywords, description)
├── /law-boundaries           Law boundary management
└── /system                   System health, alarms, backups, model eval
```

### 4.2 Queue Dashboard (`/queue`) — The Core Workbench

**Purpose**: The curator's primary screen. Shows unreviewed units one at a time for annotation.

**Layout**: Full-width workbench (optimised for keyboard)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Curation Queue   ● 47 pending    Bucket A: 23  B: 12  C: 8  D: 4         │
│                                                                           │
│  FILTERS:  [Paper: All ▼]  [Bucket: All ▼]  [Doc Type: All ▼]  [Sort ▼] │
│  ──────────────────────────────────────────────────────────────────────  │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │ #1 of 47   Unit: Q3(b)  · Nov 2024 · P1 · Suggested Answer    [A] ● ││
│  │ ──────────────────────────────────────────────────────────────────── ││
│  │ QUESTION                                    ANSWER                    ││
│  │ "ABC Ltd. entered into a long-term         "Under Ind AS 115,        ││
│  │  contract with XYZ Corp. The contract       the entity must           ││
│  │  promises delivery of software licence      identify performance      ││
│  │  and 2 years of support. Allocate the       obligations separately..."││
│  │  transaction price."                                                  ││
│  │ Marks: 12    Pages: 4-6                                               ││
│  │ ──────────────────────────────────────────────────────────────────── ││
│  │ MODEL SUGGESTION (Bucket A · Anchor: Ind AS 115)                      ││
│  │                                                                        ││
│  │ Primary:    [Ind AS 115 — Revenue Recognition  P1-P425DG] ●●●●●       ││
│  │ Secondary:  [Ind AS 116 — Leases               P1-093VHQ]             ││
│  │ Gist:       "5-step revenue recognition model for bundled contracts"   ││
│  │                                                                        ││
│  │ DECISION                                                               ││
│  │ ┌───────────────────────────────────────────────────────────────────┐ ││
│  │ │ [✓ Accept]  [✎ Edit Node]  [⊕ Add Secondary]  [✗ None Fits]  [⊘] │ ││
│  │ └───────────────────────────────────────────────────────────────────┘ ││
│  │ Keyboard: A = Accept  E = Edit  N = None Fits  X = Exclude  ← → nav  ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                           │
│  QUEUE PREVIEW (next 5)                                                   │
│  Q4(a) · Nov 2024 · P1 · SA  [A] ●●●●●                                  │
│  Q5    · Nov 2024 · P1 · QP  [B] ●●●○○   ← Disagreement between runs    │
│  Q1(c) · May 2024 · P3 · SA  [C] ●●○○○   ← 3-run tie-break              │
└──────────────────────────────────────────────────────────────────────────┘
```

**Decision actions**:

| Action | Key | What it does |
|---|---|---|
| Accept | `A` | Publishes with model's primary + secondary nodes |
| Edit | `E` | Opens node picker, curator picks primary (and optional secondary) |
| Add Secondary | `S` | Opens node picker to add a secondary tag |
| None Fits | `N` | Marks as `none_fits` — no node applies |
| Exclude | `X` | Marks as `exclude` (e.g. case stem, non-gradable) |
| Skip | `→` | Moves to next without deciding (remains in queue) |
| Undo | `U` | Reverts the last decision |

**Node picker (Edit flow)**:

```
┌──────────────────────────────────────────────────────────────────┐
│ Select primary node                    [🔍 Search...]             │
│                                                                    │
│ P1 — Financial Reporting                                          │
│   ▸ Ind AS (Standards)                                            │
│     ● Ind AS 115 — Revenue Recognition     [●●●●●]  ← Suggested  │
│       Ind AS 116 — Leases                  [●●●○○]               │
│       Ind AS 103 — Business Combinations   [●●●●○]               │
│   ▸ Standards on Audit (P3 cross-reference)                       │
│                                                                    │
│  [Confirm]  [Cancel]                                              │
└──────────────────────────────────────────────────────────────────┘
```

**Data contracts**:
```typescript
GET /api/v1/curate/queue?paper=P1&bucket=A&limit=50
→ QueueItem[] {
    unit_id, display_label, attempt_id, paper_id, doc_type_id, marks
    question_text, answer_text          // ONLY in curator API
    primary_suggestion: TagSuggestion
    secondary_suggestions: TagSuggestion[]
    bucket, method, gist, evidence
    alternatives: string[]
  }

POST /api/v1/curate/units/{unitId}/decision
body: {
  action: "accept" | "accept_alt" | "edit" | "none_fits" | "exclude"
  primary_node_id?: string
  secondary_node_ids?: string[]
  gist?: string
  seconds_spent: number
}
→ DecisionResult { action, appearance_id?, decided_at }
```

**UX priorities**:
- Keyboard-first: experienced curators review 50–100 units/hour
- Question + Answer always side by side (never stacked on desktop)
- Suggestion evidence (anchor matches, run 1 vs run 2 agreement) shown inline
- Time tracking: `seconds_spent` auto-computed per unit from focus-in to decision
- Bucket colour coding: `A=green, B=amber, C=red, D=dark`
- Auto-advance to next unit after Accept (configurable in curator settings)

---

### 4.3 Bulk Accept (`/bulk`)

**Purpose**: Accept all Bucket A suggestions for a document in one click (after spot-checking).

```
┌──────────────────────────────────────────────────────────────────┐
│ Bulk Accept — Bucket A                                            │
│                                                                    │
│ Document: CA Final Nov 2024 — P1 Suggested Answer                 │
│ Bucket A units ready: 18     Preview sample →                     │
│                                                                    │
│ ┌───────────────────────────────────────────────────────────────┐ │
│ │ Sample (5 of 18):                                             │ │
│ │ Q1(a) → Ind AS 115  ●●●●●  "Revenue from contract..."       │ │
│ │ Q2(b) → Ind AS 116  ●●●○○  "Lease modification..."          │ │
│ │ Q3    → Sec 149     ●●●●○  "Independent director quorum..." │ │
│ └───────────────────────────────────────────────────────────────┘ │
│                                                                    │
│ [✓ Accept All 18 Bucket A Units]   [Review one by one →]         │
└──────────────────────────────────────────────────────────────────┘
```

**Data contract**:
```typescript
POST /api/v1/curate/documents/{docId}/bulk_accept_bucket_a
→ { accepted_count: number, skipped_count: number }
```

---

### 4.4 Document Catalog (`/documents`)

**Purpose**: See all ingested documents, their extraction status, and manage re-ingestion.

```
┌──────────────────────────────────────────────────────────────────┐
│ Documents   [Filter: Paper ▼] [Status ▼]   [+ Add Document]      │
│                                                                    │
│ ┌─────────────────────────────────────────────────────────────┐  │
│ │  Document                   Paper  Attempt  Type    Status  │  │
│ ├─────────────────────────────────────────────────────────────┤  │
│ │  CA Final Nov 2024 P1 SA    P1     2024-11  SA     ✓ Done  │  │
│ │  CA Final Nov 2024 P1 QP    P1     2024-11  QP     ✓ Done  │  │
│ │  CA Final May 2024 P2 SA    P2     2024-05  SA     ⚠ Rev   │  │
│ │  RTP Nov 2024 P3            P3     2024-11  RTP    ⟳ Extract│  │
│ └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Data contract**:
```typescript
GET /api/v1/documents?paper=P1&status=ok&limit=50
→ DocumentListResponse { documents: DocumentSummary[], total: number }

GET /api/v1/documents/{docId}
→ DocumentDetail { document: Document, units: UnitSummary[] }
```

---

### 4.5 System Health (`/system`)

**Purpose**: Real-time dashboard showing all 5 alarms, backup status, and model evaluation.

```
┌──────────────────────────────────────────────────────────────────┐
│ System Health                     Status: ● HEALTHY  13:05 IST   │
│                                                                    │
│ ALARMS                                                            │
│  ✓ BACKUP_STALE          Last backup: 3h ago (caf_20260926.dump) │
│  ✓ ZERO_LINKS_DISCOVERED  Last run: 2024-11-01 · 47 new links    │
│  ✓ EXTRACTION_FAILURE     Failure rate: 2.1%  (< 20% threshold)  │
│  ✓ BUDGET_CAP_REACHED     No budget aborts in last 30 runs        │
│  ✓ BUCKET_A_PRECISION     Precision: 87.3%  (≥ 80% threshold)    │
│                                                                    │
│ MODEL EVALUATION                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Bucket  Samples  Agreed  Precision                       │    │
│  │   A       423     387     91.5%  ●●●●●                  │    │
│  │   B        47      31     66.0%  ●●●○○                  │    │
│  │   C        23      12     52.2%  ●●○○○                  │    │
│  └──────────────────────────────────────────────────────────┘    │
│  Gate: ✓ PASSED  (Bucket A >= 80%)                               │
│                                                                    │
│ RECENT RUNS                                                        │
│  ⟳ l3_classify    running  47/120 units   started 12:53           │
│  ✓ l2_extract     done     3 docs         11:42                   │
│  ✓ l1_fetch       done     12 files       10:15                   │
└──────────────────────────────────────────────────────────────────┘
```

**Data contracts**:
```typescript
GET /api/v1/system/health
→ SystemHealthResponse {
    status: "OK" | "WARNING" | "CRITICAL"
    alarms: Alarm[]
    evaluated_at: string
  }

GET /api/v1/system/model-evaluation?threshold=0.80
→ ModelEvaluationResponse {
    total_reviewed: number
    top1_agreement: number
    bucket_metrics: Record<string, BucketMetric>
    passed: boolean
    status_note: string
  }
```

**UX**: Alarms refresh every 60s via `setInterval` + SWR. Alarm rows animate from neutral to warning/critical state. Recent runs use SSE (Server-Sent Events) for live progress.

---

## 5. API Contract: Frontend ↔ Backend

### 5.1 Design Principles

1. **Student APIs never return `question_text` or `answer_text`** (Decision D2)
2. **Curator APIs require `X-Curator-Token` header** (separate auth)
3. **All timestamps in ISO 8601 with timezone**
4. **Node IDs are always opaque strings** (never decompose in UI)
5. **Pagination via `?limit=N&offset=M`** on all list endpoints

### 5.2 Complete API Surface

#### Student API (public, read-mostly)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/papers` | `Paper[]` with scores |
| `GET` | `/api/v1/papers/{paperId}/tree` | Full tree with importance |
| `GET` | `/api/v1/subtopics/{nodeId}` | Detail + why + appearances |
| `PUT` | `/api/v1/subtopics/{nodeId}/progress` | ProgressState |
| `GET` | `/api/v1/dashboard` | DashboardResponse |
| `GET` | `/api/v1/plan` | StudyPlanResponse |
| `GET` | `/api/v1/revision/due` | RevisionDueResponse |
| `POST` | `/api/v1/revision/{nodeId}/outcome` | next due date |
| `GET` | `/api/v1/why/subtopic/{nodeId}` | WhyResponse |
| `GET` | `/api/v1/meta` | attempt list, active scheme |

#### Curator API (internal, `X-Curator-Token` required)

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/v1/curate/queue` | `QueueItem[]` |
| `GET` | `/api/v1/curate/units/{unitId}` | Full unit detail |
| `POST` | `/api/v1/curate/units/{unitId}/decision` | DecisionResult |
| `POST` | `/api/v1/curate/units/{unitId}/undo` | UndoResult |
| `POST` | `/api/v1/curate/documents/{docId}/bulk_accept_bucket_a` | BulkResult |
| `GET` | `/api/v1/documents` | DocumentList |
| `GET` | `/api/v1/documents/{docId}` | DocumentDetail |
| `GET` | `/api/v1/system/health` | SystemHealthResponse |
| `GET` | `/api/v1/system/backups` | BackupListResponse |
| `GET` | `/api/v1/system/model-evaluation` | ModelEvaluationResponse |
| `GET` | `/api/v1/taxonomy/nodes` | Node hierarchy |
| `PUT` | `/api/v1/taxonomy/nodes/{nodeId}/descriptor` | Descriptor |

### 5.3 TypeScript Type Generation

Auto-generate types from FastAPI's OpenAPI spec:

```bash
# In CI after backend starts
curl http://localhost:8000/openapi.json > web/packages/api-client/openapi.json
npx openapi-typescript web/packages/api-client/openapi.json \
  --output web/packages/api-client/src/generated.ts
```

All API calls use the generated types — no hand-written interfaces.

---

## 6. Design Specifications

### 6.1 Colour System

```
Student App (calm, academic):
  Primary:     #1E3A5F  (navy blue — trust, depth)
  Accent:      #E8A020  (amber — importance indicators)
  Success:     #2D7D46  (green — done state)
  Warning:     #B45309  (amber — law stale, shaky)
  Background:  #F8F9FA  (off-white — easy on eyes during long study sessions)
  Surface:     #FFFFFF
  Border:      #E2E8F0

Curator Tool (focused, functional):
  Primary:     #1A1A2E  (dark navy — serious work environment)
  Bucket A:    #15803D  (green)
  Bucket B:    #D97706  (amber)
  Bucket C:    #DC2626  (red)
  Bucket D:    #6B7280  (grey)
  Background:  #0F172A  (dark mode default — reduces eye strain in long sessions)
```

### 6.2 Typography

```
Font:       Inter Variable (--font-inter)
Body:       16px / 1.6 line-height
Dense tables: 14px / 1.4 (TanStack Table rows)
Heading 1:  28px / 700
Heading 2:  22px / 600
Heading 3:  18px / 600
Code:       JetBrains Mono 14px (node IDs, fingerprints)
```

### 6.3 Importance Visual System

```typescript
// Consistent across both apps
function ImportanceDots({ score }: { score: number }) {
  const filled = Math.round(score * 5)
  return (
    <span className="flex gap-0.5">
      {[1,2,3,4,5].map(i => (
        <span key={i} className={i <= filled ? "text-amber-500" : "text-gray-300"}>●</span>
      ))}
    </span>
  )
}

// Colour bands for importance
function importanceColor(score: number): string {
  if (score >= 0.80) return "text-red-600"    // critical
  if (score >= 0.60) return "text-amber-600"  // high
  if (score >= 0.40) return "text-blue-600"   // medium
  return "text-gray-500"                       // low
}
```

### 6.4 Responsive Breakpoints

```
Mobile:   < 640px   — single column, tree as bottom drawer
Tablet:   640–1024px — 2-col grid, collapsed tree panel
Desktop:  > 1024px  — full two-pane layout
Wide:     > 1280px  — wider content, more visible in queue
```

---

## 7. UX Patterns for Speed

### 7.1 Optimistic Updates

When student marks a topic as Done:
1. UI immediately shows "Done" badge (optimistic)
2. PUT request fires in background
3. On success: confirm
4. On failure: revert with toast "Failed to save, retrying..."

### 7.2 Skeleton Loaders (Never Blank Screens)

Every async boundary has a skeleton:
```tsx
<Suspense fallback={<SubtopicSkeleton />}>
  <SubtopicDetail nodeId={nodeId} />
</Suspense>
```

### 7.3 Keyboard Navigation in Curator

The queue workbench is fully keyboard-operable:
```
A         → Accept
E         → Edit (opens node picker)
N         → None Fits
X         → Exclude
→ / L     → Next unit
← / H     → Previous unit
U         → Undo last decision
?         → Help overlay
```
A `useKeyboardShortcuts()` hook registers and documents all bindings.

### 7.4 Infinite Queue (No Pagination)

The queue uses TanStack Query's `useInfiniteQuery` with a virtual scroller (TanStack Virtual). Curators see the queue preview as a vertical list; clicking any row jumps to that unit. No "Next Page" button.

---

## 8. Customer Demo / Showcase Version

For customer demos before real data is available, seed a demo mode:

```typescript
// web/apps/student/app/demo/page.tsx
// Renders with synthetic but realistic data:
// - 6 papers with pre-filled importance scores
// - 12 subtopics with a mix of Done/In Progress/Not Started
// - 3-day study plan
// - 4 revision items due
// - Real WhyResponse breakdowns
```

The demo mode is toggled by `?demo=true` query param or `NEXT_PUBLIC_DEMO_MODE=true` env var. It bypasses the FastAPI backend entirely and uses local JSON fixtures. This lets you show the customer a live, polished UI without needing any database setup.

---

## 9. Implementation Phases

### Phase 1 — Foundation (1 week)
- Turborepo setup: `apps/student`, `apps/curator`, `packages/ui`, `packages/api-client`
- Shared Tailwind config + shadcn/ui component scaffold
- OpenAPI type generation pipeline
- FastAPI CORS + authentication middleware updates

### Phase 2 — Student App Core (2 weeks)
- Dashboard + Papers list
- Paper detail tree with importance visualisation
- Subtopic detail panel + Why breakdown
- Progress tracking (optimistic updates)
- Mobile responsive layout

### Phase 3 — Curator Workbench (2 weeks)
- Queue view with unit detail panel
- Decision actions + keyboard shortcuts
- Node picker (search + hierarchy browse)
- Bulk accept view
- System health dashboard

### Phase 4 — Student App Intelligence (1 week)
- Study plan with day-by-day view
- Revision queue
- Performance/mock test history

### Phase 5 — Polish & Demo Mode (1 week)
- Demo mode with synthetic data
- Animations + skeleton loaders
- E2E tests (Playwright)
- PWA manifest for mobile install

---

## 10. Contract Enforcement Between Frontend and Backend

### 10.1 Automated Drift Detection

```yaml
# .github/workflows/openapi-check.yml
- name: Check OpenAPI drift
  run: |
    curl http://localhost:8000/openapi.json > /tmp/current.json
    diff web/packages/api-client/openapi.json /tmp/current.json
    if [ $? -ne 0 ]; then
      echo "OpenAPI spec has changed — regenerate types and commit"
      exit 1
    fi
```

### 10.2 Runtime Zod Validation

All API responses are validated with Zod schemas at the boundary:

```typescript
// packages/api-client/src/schemas.ts
import { z } from "zod"

export const SubtopicScoreSchema = z.object({
  node_id: z.string(),
  importance: z.number().min(0).max(1),
  exam_score: z.number(),
  practice_score: z.number(),
  weight_prior: z.number(),
  freq_hits: z.number().int(),
})

// In API client:
const response = await fetch(url)
const data = SubtopicScoreSchema.parse(await response.json())
// Throws ZodError in dev if backend returns unexpected shape
```

### 10.3 D2 Compliance Enforced at Client Type Level

```typescript
// Student API types never include question/answer text
interface SubtopicAppearance {
  attempt_id: string
  marks: number | null
  law_stale: boolean
  display_label: string
  // NO question_text or answer_text — enforced by generated type
}

// Curator type explicitly adds it
interface CuratorQueueItem extends Omit<SubtopicAppearance, never> {
  question_text: string   // only in curator API client
  answer_text: string | null
}
```
