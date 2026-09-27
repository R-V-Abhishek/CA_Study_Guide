# CA Final Study Companion — UI System Design & Implementation Plan

> **Version**: 2.0 | **Date**: September 2026
> **Backend**: FastAPI + PostgreSQL (L0–L5 complete, M9 is the UI)
> **Key decision**: Two completely separate apps with different visual language, different UX paradigm, and different design goals. They share an API client package and Zod schemas, but not component libraries.

---

## 0. Design Philosophy

### Two apps, two jobs

| | Student Study App | Curator Annotation Tool |
|---|---|---|
| **User** | A stressed CA Final student | You (the operator) |
| **Session type** | 1–3 h focused study, daily | 30-min burst queue burn-down |
| **Primary emotion to target** | Calm focus + earned progress | Efficiency, accuracy, speed |
| **Interface model** | Consumer app — warm, motivational | Power tool — keyboard-driven, dense |
| **Mobile importance** | Desktop-first; tablet/phone secondary | Desktop only |
| **Information density** | Low-to-medium | High |
| **Dark mode** | User preference toggle | Dark by default |
| **Animation** | Purposeful: celebrates progress, guides attention | Minimal: never slow the workflow |
| **Gamification** | Yes — streaks, milestones, progress rings | No |
| **Design inspiration** | Anki + Duolingo + Linear | Linear + Raycast + GitHub Issues |

**Rule**: These two apps should look like they came from different design teams. Do not share a component library. Share only type-safe API clients and Zod validation schemas.

---

## 1. Monorepo Structure

```
web/
├── apps/
│   ├── student/              # Student Study App — consumer product
│   └── curator/              # Annotation Tool — internal power tool
├── packages/
│   ├── api-client/           # Generated TS types + Zod schemas + fetch wrappers
│   └── ts-config/            # Shared TypeScript config only
├── package.json              # Turborepo workspaces
└── turbo.json
```

**No shared UI package.** Each app has its own `components/` directory. The visual language is intentionally divergent.

---

## 2. Toolchain

```
Both apps:
  Runtime:        Node LTS, pnpm, Vite (NOT Next.js — see rationale below)
  Framework:      React 18 + TypeScript
  Router:         React Router v6 (file-based routing)
  State/Cache:    TanStack Query v5 (server state) + Zustand (client state)
  Forms:          React Hook Form + Zod
  API types:      openapi-typescript (auto-generated) + openapi-fetch
  Testing:        Vitest + Playwright (E2E)

Student app additions:
  Styling:        Tailwind CSS 4 + custom design tokens (no component framework)
  Icons:          Lucide React
  Animation:      Motion (formerly Framer Motion) — purposeful only
  Charts:         Recharts
  Rich text:      Tiptap (notes editor — ProseMirror-based, lightweight)
  Markdown:       react-markdown + remark-gfm (for rendering saved notes)
  Fonts:          Geist (body) + Geist Mono (code/node IDs)

Curator app additions:
  Styling:        Tailwind CSS 4
  Icons:          Lucide React
  Tables:         TanStack Table v8 (headless, fully typed)
  Fonts:          Inter (body) + JetBrains Mono (IDs, fingerprints)
  Hotkeys:        tinykeys (tiny, typed keyboard shortcut library)
```

### Why Vite, not Next.js?

The original spec chose Next.js for SSR/ISR. After reconsideration:

- This is a **private, single-user tool**. SEO is irrelevant. ISR buys nothing for content that changes when you run `caf intel recompute`.
- The FastAPI backend is already the server. The UI is a SPA that talks to it. Adding a Node.js middleware layer (Next.js) creates an unnecessary runtime dependency.
- Vite builds faster, debugs simpler, and deploys as a static bundle served directly by FastAPI's static file mount or nginx.
- TanStack Query handles all caching — the ISR story from Next.js is not needed.

---

## 3. Student Study App — `apps/student`

### 3.1 Design Language

#### Colour System

```
Light mode (default):
  Background:       #FAFAF9     warm off-white — easy on eyes during long sessions
  Surface:          #FFFFFF
  Surface-raised:   #F5F5F4     slightly lifted cards
  Border:           #E7E5E4     warm stone border
  Text-primary:     #1C1917     warm near-black
  Text-secondary:   #78716C     warm stone-500
  Text-muted:       #A8A29E     stone-400

  Brand-primary:    #4F46E5     indigo — focus, intellect
  Brand-secondary:  #7C3AED     violet — emphasis
  Accent-warm:      #EA580C     orange — importance indicators, streaks

  Success:          #16A34A     green-600 — done state
  Warning:          #D97706     amber-600 — law stale, overdue
  Danger:           #DC2626     red-600 — critical importance, overdue revision
  Info:             #0284C7     sky-600 — secondary info

  Importance-critical:  #DC2626   (score ≥ 0.80)
  Importance-high:      #EA580C   (score ≥ 0.60)
  Importance-medium:    #CA8A04   (score ≥ 0.40)
  Importance-low:       #6B7280   (score < 0.40)

Dark mode (toggle):
  Background:       #0C0A09
  Surface:          #1C1917
  Surface-raised:   #292524
  Border:           #44403C
  Text-primary:     #FAFAF9
  Text-secondary:   #A8A29E
  (accent/status colours identical — they're already vibrant enough)
```

#### Typography

```
Font-body:          Geist, 'Inter Variable', system-ui, sans-serif
Font-mono:          'Geist Mono', 'JetBrains Mono', monospace

Body:               15px / 1.65 line-height (slightly larger for comfortable reading)
Body-small:         13px / 1.5
Heading-1:          30px / 700 / tracking-tight
Heading-2:          22px / 600
Heading-3:          17px / 600
Heading-4:          15px / 600
Caption:            12px / 500 / uppercase / tracking-wide
Mono:               13px (node IDs, fingerprints, dates)
```

#### Motion Principles

- **Progress milestones celebrate**: completing a chapter triggers a confetti burst (canvas-confetti, < 3KB). Completing a paper triggers a full-screen celebration moment.
- **State transitions are fast**: 150ms for most UI state changes. Not flashy.
- **Skeleton loaders only**: no spinner anywhere. Every async boundary has a content-shaped skeleton.
- **Hover prefetch**: hovering a subtopic for 200ms prefetches its detail panel.
- **No infinite animation**: no pulsing, no breathing, no loading spinners that keep going. Animation is a punctuation mark, not wallpaper.

#### Importance Visual System

```tsx
// Five-dot system — consistent throughout
function ImportanceDots({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const filled = Math.round(score * 5)
  const color = score >= 0.80 ? "text-red-600"
              : score >= 0.60 ? "text-orange-500"
              : score >= 0.40 ? "text-amber-500"
              : "text-stone-300"
  const sizes = { sm: "text-xs gap-0.5", md: "text-sm gap-1", lg: "text-base gap-1" }
  return (
    <span className={`inline-flex items-center ${sizes[size]}`} title={`Importance: ${Math.round(score * 100)}%`}>
      {[1,2,3,4,5].map(i => (
        <span key={i} className={i <= filled ? color : "text-stone-200 dark:text-stone-700"}>●</span>
      ))}
    </span>
  )
}
```

---

### 3.2 Information Architecture

```
/ (Home — Dashboard)
├── /papers                           Papers overview
│   └── /papers/:paperId              Paper detail
│       └── /papers/:paperId/:nodeId  Subtopic detail (deep-link)
├── /plan                             Weekly study plan
├── /revision                         Spaced revision — one card at a time
├── /progress                         Full coverage view across all papers
├── /mock                             Mock test log + paper-wise trend
└── /settings                         Target attempt, hours/day, revision intervals
```

Deep-linking to a subtopic works directly: `/papers/P1/P1-7KQ2MX` renders the paper tree with that subtopic pre-selected and scrolled into view.

---

### 3.3 Home Dashboard (`/`)

**Purpose**: Answer "What should I study right now?" within 2 seconds of opening the app. Motivate, not overwhelm.

**Layout**: Single-column hero section + two-column grid below. Desktop: max-width 1200px centred.

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Streak flame 🔥 14]    Good evening. 47 days to Nov 2026.         │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  TODAY'S FOCUS                                               │   │
│  │  ──────────────────────────────────────────────────────────  │   │
│  │  ① Ind AS 115 — Revenue Recognition          45 min  ●●●●●  │   │
│  │     P1 · Not started · Asked 6× (12–16 marks)   [Study →]   │   │
│  │  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  │   │
│  │  ② SA 700 — Auditor's Report                 30 min  ●●●●○  │   │
│  │     P3 · In progress · Asked 5× (8–12 marks)    [Continue→]  │   │
│  │  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  │   │
│  │  ③ Sec 44AB — Tax Audit                       30 min  ●●●●○  │   │
│  │     P4 · Not started · Weak flag ⚑                [Study →]   │   │
│  │                                                               │   │
│  │  [Full study plan →]                  Revision due: 3 today  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────┐    ┌─────────────────────────────────┐    │
│  │  COVERAGE             │    │  REVISION DUE                   │    │
│  │                        │    │                                 │    │
│  │  Overall  ████░░  58%  │    │  Ind AS 116 — Leases    P1     │    │
│  │  Group 1  ████░░  61%  │    │  Last: 21 days ago             │    │
│  │  Group 2  ████░░  54%  │    │                                 │    │
│  │                        │    │  Sec 149 — Ind. Director  P2   │    │
│  │  P1  ████░░  60%  →   │    │  Last: 7 days ago               │    │
│  │  P2  █████░  72%  →   │    │                                 │    │
│  │  P3  ███░░░  48%  →   │    │  + 1 more                       │    │
│  │  P4  ███░░░  51%  →   │    │  [Open revision queue →]        │    │
│  │  P5  ██░░░░  38%  →   │    └─────────────────────────────────┘    │
│  │  P6  ██████  90%  →   │                                           │
│  └──────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- "Today's Focus" is the single most important element. It appears above the fold regardless of viewport height. Max 3–5 items.
- The streak counter at the top is a flame icon (`🔥`) with the day count. Resets if no subtopic is marked done in a calendar day. Simple to implement, disproportionately motivating.
- Coverage bars animate from left on first render (150ms ease-out). On subsequent visits, they don't re-animate.
- Weak-flag subtopics (`⚑`) appear in the Today's Focus if they're not started and the exam is < 60 days away.
- The "Revision due" tile collapses if there's nothing due today (replaced by "Nothing due — well done ✓").
- No numeric importance scores on the dashboard. Use dots and human labels only.

**Data contracts**:
```typescript
GET /api/v1/dashboard
→ DashboardResponse {
    greeting: string                        // "Good evening" — computed by backend (IST time)
    days_to_exam: number | null
    streak_days: number
    coverage: CoverageResponse {
      overall_pct: number
      group1_pct: number
      group2_pct: number
      papers: { paper_id, paper_code, paper_name, coverage_pct, revision_due_count }[]
    }
    plan_preview: PlanItem[]               // top 3–5 items
    revision_due_count: number
    revision_due_preview: RevisionItem[]   // top 2 due items for preview tile
  }
```

---

### 3.4 Papers Overview (`/papers`)

**Purpose**: Entry point to each of the 6 papers. Conveys health at a glance.

**Layout**: 3-column card grid on desktop (> 1024px), 2-column on tablet, 1-column on mobile.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Papers                                   [Group: All ▼]  [Sort ▼]   │
│                                                                        │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────┐  │
│  │ P1                  │  │ P2                  │  │ P3            │  │
│  │ Financial Reporting │  │ Adv. Financial Mgmt │  │ Auditing &    │  │
│  │                     │  │                     │  │ Assurance     │  │
│  │  [Progress ring 60%]│  │  [Progress ring 72%]│  │  [ring 48%]   │  │
│  │                     │  │                     │  │               │  │
│  │  Avg importance     │  │  Avg importance     │  │  Avg imp.     │  │
│  │  ●●●●○              │  │  ●●●○○              │  │  ●●●●○        │  │
│  │                     │  │                     │  │               │  │
│  │  39 subtopics       │  │  41 subtopics       │  │  37 subtopics │  │
│  │  8 revision due     │  │  2 revision due     │  │  0 due        │  │
│  │  3 weak flags ⚑    │  │  1 weak flag ⚑     │  │               │  │
│  │                     │  │                     │  │               │  │
│  │  [Open →]           │  │  [Open →]           │  │  [Open →]     │  │
│  └─────────────────────┘  └─────────────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- **Progress ring**: circular SVG progress indicator (not a bar). More visually distinctive than a bar. Colour transitions from red (0–33%) through amber (33–66%) to green (66–100%) based on coverage.
- Cards are clickable in their entirety (large tap target).
- Weak flag count (⚑) is only shown if > 0, styled in orange.
- Revision due count is only shown if > 0, styled in amber.
- Sort options: by Group (default), by Coverage % ascending (find the weakest), by Average Importance descending.

**Data contract**:
```typescript
GET /api/v1/papers
→ Paper[] {
    id, code, name, group_no
    coverage_pct: number
    avg_importance: number
    subtopic_count: number
    revision_due_count: number
    weak_flag_count: number
  }
```

---

### 3.5 Paper Detail (`/papers/:paperId`)

**Purpose**: The core study screen. Navigate the syllabus, see importance, track progress.

**Layout**: Two-pane — persistent left sidebar (syllabus tree) + main content area. Desktop ≥ 1024px only for two-pane; below that, the tree collapses to a sheet/drawer opened via a button.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ← Papers   P1: Financial Reporting                [60% ████░░] [⚑ 3]    │
├─────────────────────┬────────────────────────────────────────────────────┤
│ SYLLABUS TREE       │  ← Select a subtopic                               │
│  [🔍 Filter topics] │                                                     │
│  [Sort: Importance▼]│                                                     │
│                     │  When nothing is selected, show:                    │
│  Ch 1: Ind AS ●●●●● │  - paper coverage ring                             │
│   ▼ Ind AS 115 ●●●●●│  - top 5 importance leaders                        │
│      [in-progress ●]│  - 3 weak-flag alerts                              │
│   ▼ Ind AS 116 ●●●○ │  - revision due for this paper                     │
│      [not started ○]│                                                     │
│   ▶ Ind AS 103 ●●●●○│                                                     │
│                     │                                                     │
│  Ch 2: Companies ●●●│                                                     │
│   ▶ Sec 149    ●●●●○│                                                     │
│   ▶ Sec 168    ●●●○○│                                                     │
│                     │                                                     │
│  Ch 3: Audit Stds ●●│                                                     │
│   ▶ SA 700     ●●●●○│                                                     │
│   ▶ SA 240     ●●○○○│                                                     │
│                     │                                                     │
│  [Show all chapters]│                                                     │
│                     │                                                     │
│  FILTERS            │                                                     │
│  ○ All              │                                                     │
│  ○ Not started      │                                                     │
│  ○ In progress      │                                                     │
│  ○ Weak flags only  │                                                     │
└─────────────────────┴────────────────────────────────────────────────────┘
```

**Tree node anatomy**:
```
  ▼ Ind AS 115 — Revenue Recognition    ●●●●●   [●  in progress]
```
- Triangle: expand/collapse topics under a chapter
- Name (truncated at 40 chars with tooltip)
- Importance dots (right-aligned)
- Progress badge: `○ not started`, `● in progress`, `✓ done` — inline, compact

**Chapter-level rows**: non-clickable. Show chapter name + average importance. Clicking opens/closes the topic list.

**Topic-level rows**: clickable. Select the topic in the main panel (shows topic-level summary: subtopics list with their importances).

**Subtopic-level rows**: clickable. Loads subtopic detail in the main panel.

**Sort options**:
- `Importance DESC` (default): critical stuff first
- `Syllabus order`: ICAI's `seq` field — for systematic study
- `Progress: Not done first`: surfaces unfinished work

**Data contract**:
```typescript
GET /api/v1/papers/:paperId/tree
→ PaperTreeResponse {
    paper: Paper
    chapters: {
      id, name, seq, avg_importance
      topics: {
        id, name, seq, importance, progress_status
        subtopics: {
          id, name, seq, importance, freq_hits
          progress_status: "not_started" | "in_progress" | "done"
          law_stale: boolean
          weak: boolean
          revision_due: boolean
        }[]
      }[]
    }[]
  }
```

---

### 3.6 Subtopic Detail Panel

**Purpose**: Everything about one subtopic. Loaded in the right pane on desktop, full page on mobile.

**Layout** (desktop — right panel):

```
┌────────────────────────────────────────────────────────────────────┐
│ P1 › Ind AS › Chapter 1                                            │
│                                                                     │
│ Ind AS 115 — Revenue Recognition                                   │
│ ●●●●●  Critical  ·  Asked 6× (2019–2025)  ·  12–16 marks typical  │
│                                                                     │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │  STATUS                                                       │   │
│ │  [○ Not started] [● In progress] [✓ Done]  ← toggle buttons  │   │
│ │  Last revised: —                                              │   │
│ └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│ WHY IS THIS IMPORTANT?                                              │
│ ─────────────────────                                               │
│ Asked in 6 of the last 8 exams. Section weightage: 12–18%.         │
│ Most recent: Nov 2025 (16 marks). Appeared in 2 RTPs.              │
│ [See full breakdown ▾]    ← expands E/P/W math on demand           │
│                                                                     │
│ ⚑ WEAK FLAG                                                        │
│ Asked 6×, last 8 exams. Status: Not started.                       │
│ Exam in 47 days — study this soon.                                  │
│                                                                     │
│ ⚠ LAW STATUS                                                       │
│ Current law — no applicability issues for Nov 2026.                 │
│                                                                     │
│ PAST APPEARANCES (6 total)                                          │
│ ─────────────────────────                                           │
│  Nov 2025  ·  SA · Q3(b)  ·  16 marks                              │
│  May 2025  ·  RTP · Q2(a)  ·  12 marks                             │
│  Nov 2024  ·  SA · Q1(a)  ·  16 marks                              │
│  May 2024  ·  MTP S2 · Q4  ·  8 marks   ← practice signal          │
│  Nov 2023  ·  SA · Q5(b)  ·  12 marks                              │
│  [Show all 6 →]                                                     │
│                                                                     │
│ NOTES                                                               │
│ ─────                                                               │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │  [Bold] [Italic] [Code] [Bullet] [Numbered] [H3] [Divider]   │   │
│ │  ─────────────────────────────────────────────────────────── │   │
│ │                                                              │   │
│ │  The 5-step model:                                          │   │
│ │  1. Identify the contract                                   │   │
│ │  2. Identify performance obligations                        │   │
│ │  …                                                          │   │
│ │                                                              │   │
│ └──────────────────────────────────────────────────────────────┘   │
│  [Auto-saved]                                                       │
└────────────────────────────────────────────────────────────────────┘
```

**Status toggle**: Three-segment button (not a dropdown). Tap/click to cycle or jump directly. When marked "Done":
- Progress row updates immediately (optimistic).
- If this is the first time marking this subtopic done for a paper, a small confetti burst fires.
- If this is the last subtopic in a chapter, a "Chapter complete!" toast with a firework emoji appears.
- If this is the last subtopic in the paper, a full-page celebration modal fires.

**"Why is this important?" accordion**:
- Collapsed by default. Human-readable summary (plain English) always visible.
- Expanded view shows the E/P/W/I score breakdown with bar charts (not tables). Makes the math understandable.

**Weak flag**: Only shown if the flag is active. Styled with an orange left border card.

**Law status**: Only shown if `law_stale = true` OR to confirm applicability for exam-type docs. Uses amber for stale.

**Past appearances**: Sorted descending by attempt date. Exam (SA, QP) vs Practice (RTP, MTP) differentiated by a subtle tag. `law_stale` appearances marked with `⚠ stale law` badge. Limited to 5, with "Show all" expansion. The question text and answer text are **not shown** here (D2 compliance — student API never returns those fields).

**Notes editor (Tiptap)**:
- Toolbar: Bold, Italic, Inline code, Bullet list, Numbered list, H3, Divider.
- Autosave with 2-second debounce via `PUT /api/v1/subtopics/:nodeId/notes`.
- "Auto-saved" indicator updates after successful save. Shows "Saving…" during the request.
- Supports Markdown shortcuts: `**bold**`, `_italic_`, `# H3`, `- bullet`.
- Maximum practical length: ~10,000 characters. No hard enforced limit.

**Data contracts**:
```typescript
GET /api/v1/subtopics/:nodeId
→ SubtopicDetailResponse {
    node: { id, name, paper_id, paper_code, chapter_name, topic_name, seq }
    score: {
      importance: number
      exam_score: number
      practice_score: number
      weight_prior: number
      freq_hits: number
      freq_window: number
    }
    why: {
      summary: string                        // human-readable, ≤ 60 words
      drivers: WhyDriver[]                   // for expandable breakdown
    }
    appearances: AppearanceSummary[] {
      attempt_id, attempt_label, doc_type_id, display_label
      marks: number | null
      law_stale: boolean
      signal_class: "exam" | "practice"
    }
    progress: {
      status: "not_started" | "in_progress" | "done"
      first_done_at: string | null
      last_revised_at: string | null
    }
    notes: string | null                     // raw Tiptap JSON or null
    law_stale: boolean
    weak: boolean
    applicable: boolean
  }

PUT /api/v1/subtopics/:nodeId/progress
body: { status: "not_started" | "in_progress" | "done" }
→ ProgressState

PUT /api/v1/subtopics/:nodeId/notes
body: { body: string }                       // Tiptap JSON
→ { updated_at: string }
```

---

### 3.7 Study Plan (`/plan`)

**Purpose**: See exactly what to study, day by day, for the coming week.

**Layout**: Timeline-style. Sticky header with controls; scrollable day cards.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Study Plan                                                            │
│                                                                       │
│  Per day: [2 hrs ▼]   Papers: [All ▼]   [Regenerate ↺]             │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                       │
│  TODAY — Monday, Sep 30, 2026                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ① Ind AS 115 — Revenue Recognition          45 min  ●●●●●    │  │
│  │     P1 · Not started · Asked 6× · 12–16 marks usually         │  │
│  │     [Start →]                                                  │  │
│  │  ──────────────────────────────────────────────────────────── │  │
│  │  ② SA 700 — Auditor's Report                 30 min  ●●●●○    │  │
│  │     P3 · In progress · Asked 5×                               │  │
│  │     [Continue →]                                               │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  TUESDAY — Oct 1, 2026                                                │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ① Sec 44AB — Tax Audit                      45 min  ●●●●○   │  │
│  │  ② CARO 2020                                 30 min  ●●●●○   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  [Next week →]                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- Clicking `[Start →]` navigates to `/papers/P1/P1-7KQ2MX` (subtopic deep-link).
- When a plan item is marked Done in the subtopic view, the plan refreshes and shows a strikethrough on that item.
- "Regenerate" is a manual trigger. The plan is not live-regenerated on every visit — only on demand or when the student changes `hours/day` or paper filters.
- Completed items stay visible with a strikethrough + grey style. They are not hidden.

**Data contract**:
```typescript
GET /api/v1/plan?hours=2&days=7&papers=P1,P2,P3
→ StudyPlanResponse {
    generated_at: string
    per_day_minutes: number
    days: DayPlan[] {
      date: string
      is_today: boolean
      items: PlanItem[] {
        node_id, node_name, paper_id, paper_code
        estimated_minutes: number
        importance: number
        progress_status: string
        reason: string         // "Asked in 6 of last 8 exams; weightage 12–18%"
      }
    }
  }
```

---

### 3.8 Revision Queue (`/revision`)

**Purpose**: Focused spaced-repetition review. One card at a time. Feels deliberate, not like a task manager.

**Layout**: Single-card, full-screen-ish. Like Anki — the card is the whole UI.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ← Back   Revision Queue                   3 of 5 due today           │
│                                                                       │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │                                                                │   │
│ │  P1 · Chapter 1 · Ind AS                                      │   │
│ │  ─────────────────────────────────────────────────────────    │   │
│ │                                                                │   │
│ │  Ind AS 116 — Leases                     ●●●○○               │   │
│ │                                                                │   │
│ │  Last studied: 21 days ago                                    │   │
│ │  Interval: 21 days (Revision 3 of 4)                          │   │
│ │                                                                │   │
│ │  ─────────────────────────────────────────────────────────    │   │
│ │                                                                │   │
│ │  Your notes (tap to expand):                                  │   │
│ │  > Lessee: ROU asset + lease liability on commencement date…  │   │
│ │                                                                │   │
│ │  ─────────────────────────────────────────────────────────    │   │
│ │                                                                │   │
│ │  How well do you remember this?                               │   │
│ │                                                                │   │
│ │  ┌──────────────────────┐  ┌──────────────────────────────┐  │   │
│ │  │   ✓  Got it          │  │   ≈  Shaky — reset           │  │   │
│ │  └──────────────────────┘  └──────────────────────────────┘  │   │
│ │                                                                │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  Upcoming (next 7 days): 12 topics                                    │
│  [Skip to overview →]                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- This screen should feel quiet. No sidebar, no navigation chrome beyond the back button.
- Tapping the notes preview expands it inline (not a new page).
- "Got it" advances to the next interval. "Shaky" resets to interval 0. Both auto-advance to the next card after a 400ms pause (so the choice registers visually).
- When all due items are cleared: a congratulatory screen — "All done for today! 🎉 Next revision in 3 days." — not just a blank list.
- Upcoming tile at the bottom is informational, not interactive.

**Data contracts**:
```typescript
GET /api/v1/revision/due
→ RevisionDueResponse {
    due_today: RevisionItem[] {
      node_id, node_name, paper_id, paper_code
      due_date: string
      interval_days: number
      interval_stage: number
      importance: number
      notes_preview: string | null    // first 100 chars of plain text
    }
    upcoming_7d_count: number
  }

POST /api/v1/revision/:nodeId/outcome
body: { outcome: "ok" | "shaky" }
→ { next_due_date: string, next_interval_days: number }
```

---

### 3.9 Progress Overview (`/progress`)

**Purpose**: Comprehensive view of all 264 subtopics — where you've been, where you haven't.

**Layout**: Accordion by paper, expandable to show chapter-level progress bars, further expandable to subtopic rows.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Progress Overview                                                     │
│                                                                       │
│  Overall coverage: 58%    ████████████░░░░░░░░                       │
│  Group 1: 61%  Group 2: 54%                                           │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                       │
│  [Filter: All ▼]   [Sort: Coverage asc ▼]   [Export CSV]            │
│                                                                       │
│  ▼ P1: Financial Reporting  ···  60%  ████████████░░░░               │
│    ▼ Chapter 1: Ind AS  ···  52%  ●●●●●                              │
│       Ind AS 115  ●●●●●  [● in progress]                             │
│       Ind AS 116  ●●●○○  [○ not started]                             │
│       Ind AS 103  ●●●●○  [✓ done]                                    │
│    ▶ Chapter 2: Companies Act  ···  71%  ●●●●○                       │
│    ▶ Chapter 3: Audit Standards  ···  45%  ●●●○○                     │
│                                                                       │
│  ▶ P2: Adv. Financial Mgmt  ···  72%  ████████████████░░            │
│  ▶ P3: Auditing  ···  48%  ██████████░░░░░░░░░░                     │
└──────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- Papers collapsed by default. Clicking expands to chapters, clicking a chapter expands to subtopics.
- "Export CSV" outputs: subtopic name, paper, chapter, importance, status, first_done_at, last_revised_at.
- Filter options: All, Not started, In progress, Done, Weak flags, Law stale.

---

### 3.10 Mock Test Log (`/mock`)

**Purpose**: Log self-attempted mock test scores. See trend.

**Layout**: Simple. Score entry form + paper-wise trend charts.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Mock Test Log          [+ Log Score]                                  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ P1: Financial Reporting                                       │   │
│  │ Scores: 52 → 61 → 68  (last 3 MTPs)                         │   │
│  │ [Sparkline chart]                                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  HISTORY                                                              │
│  ─────────────────────────────────────────────────────────────────  │
│   Date         Paper    Attempt      Score                            │
│   Sep 2026     P1       MTP Sep 26   68/100                          │
│   Aug 2026     P1       MTP May 26   61/100                          │
│   Jul 2026     P1       MTP Nov 25   52/100                         │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 3.11 Settings (`/settings`)

Minimal. Four fields:
- Target exam attempt (dropdown populated from `GET /api/v1/meta`)
- Exam date (date picker)
- Study hours per week (number input)
- Revision intervals (comma-separated days, default: `3,7,21,60`)

---

### 3.12 Responsive Behaviour (Desktop-first)

| Breakpoint | Layout |
|---|---|
| ≥ 1280px (wide desktop) | Full two-pane on paper detail. Max-width 1200px on dashboard. |
| 1024–1279px (desktop) | Two-pane, slightly compressed sidebar (200px). |
| 768–1023px (tablet) | Paper detail: single column. Tree panel opens as a sheet (left-slide). |
| < 768px (mobile) | Single column. Tree as a bottom sheet. Subtopic detail full page. |

**Mobile-specific decisions**:
- Bottom navigation bar (5 items: Home, Papers, Plan, Revision, Progress). Replaces the sidebar nav.
- Paper tree becomes a full-screen modal with search/filter. Tapping a subtopic closes the modal and loads the detail screen.
- Notes editor is full-screen on mobile (no inline expansion).
- Dashboard cards stack vertically. "Today's Focus" is the very first thing.

---

### 3.13 PWA Specification

```json
// student/public/manifest.json
{
  "name": "CA Final Study Companion",
  "short_name": "CA Study",
  "description": "Your exam intelligence platform for CA Final",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#FAFAF9",
  "theme_color": "#4F46E5",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [],
  "categories": ["education", "productivity"]
}
```

**Service Worker strategy**: Cache-first for static assets. Network-first with fallback for API routes. Offline state: the app renders with cached data and shows a "Offline — showing last synced data" banner. Progress updates are queued locally and synced when connectivity returns (using Background Sync API where supported; localStorage queue otherwise).

---

## 4. Curator Annotation Tool — `apps/curator`

### 4.1 Design Language

```
Dark mode, always. The curator works in long focused sessions.
Background:     #0F172A     slate-900
Surface:        #1E293B     slate-800
Surface-raised: #334155     slate-700
Border:         #475569     slate-600
Text-primary:   #F1F5F9     slate-100
Text-secondary: #94A3B8     slate-400
Text-muted:     #64748B     slate-500

Bucket A (high confidence, accept):  #15803D  green-700 / bg #166534
Bucket B (some conflict):            #B45309  amber-700 / bg #92400E
Bucket C (tie-break):                #B91C1C  red-700 / bg #7F1D1D
Bucket D (no consensus):             #4B5563  gray-600 / bg #374151

Success:   #22C55E   green-500
Warning:   #F59E0B   amber-500
Danger:    #EF4444   red-500
Info:      #60A5FA   blue-400

Font: Inter (body) + JetBrains Mono (IDs, fingerprints, gists)
```

**Animation**: None beyond instant state transitions (< 100ms). Every millisecond of animation cost adds up across 100 annotations.

---

### 4.2 Information Architecture

```
/ (Queue Dashboard)
├── /queue                      Curation queue — main workbench
│   └── /queue/:unitId          Single-unit detail (keyboard-navigable)
├── /bulk                       Bulk accept Bucket A view
├── /documents                  Document catalogue
│   └── /documents/:docId       Document detail + unit list
├── /taxonomy                   Taxonomy browser
│   └── /taxonomy/:nodeId       Node descriptor editor
├── /law-boundaries             Law boundary configuration
└── /system                     System health, alarms, runs, backups, model eval
```

---

### 4.3 Queue Workbench (`/queue`)

**Purpose**: The primary screen. Review one unit at a time. Keyboard-first.

**Layout**: Full-width. No sidebar. Maximum content density.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Curation Queue  ● 47 pending  [A 23 green] [B 12 amber] [C 8 red] [D 4] │
│                                                                            │
│  [Paper: All ▼]  [Bucket: All ▼]  [Doc Type: All ▼]  [Attempt: All ▼]   │
│  ─────────────────────────────────────────────────────────────────────── │
│                                                                            │
│  UNIT 1 of 47                        [A] BUCKET A — ANCHOR CONSENSUS      │
│  Nov 2024 · P1 · Suggested Answer                                         │
│  Q3(b) · 12 marks · Pages 4–6       [Time on unit: 00:23]                │
│  ─────────────────────────────────────────────────────────────────────── │
│                                                                            │
│  QUESTION                              │  ANSWER                           │
│  ─────────────────────────────────────  ─────────────────────────────    │
│  ABC Ltd. entered into a long-term     Under Ind AS 115, the entity        │
│  contract with XYZ Corp. The contract  must identify performance            │
│  promises delivery of software         obligations separately. The          │
│  licence and 2 years of support.       transaction price is allocated       │
│  Allocate the transaction price.       based on standalone selling          │
│                                        prices using the residual            │
│                                        approach if SSP is observable…      │
│                                                                            │
│  SUGGESTION (Anchor: IndAS:115 · R1 ≡ R2)                                │
│  ─────────────────────────────────────────────────────────────────────── │
│  Primary:   [Ind AS 115 — Revenue Recognition   P1-P425DG]  ●●●●●        │
│  Secondary: [Ind AS 108 — Operating Segments    P1-093VHQ]                │
│  Gist:      "5-step revenue recognition for bundled contracts"             │
│  Evidence:  IndAS:115 (×4 mentions) · R1 agrees R2 · Chapter: Ind AS     │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────── │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  [A] Accept   [E] Edit   [S] Add Secondary   [N] None Fits          │ │
│  │  [X] Exclude  [U] Undo   [→] Skip   [?] Help                        │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  QUEUE PREVIEW ──────────────────────────────────────────────────────    │
│  Q4(a) · Nov 2024 · P1 · SA  [A]  IndAS:116 anchor · consensus            │
│  Q5    · Nov 2024 · P1 · QP  [B]  R1 vs R2 disagree ← conflict           │
│  Q1(c) · May 2024 · P3 · SA  [C]  3-run tie-break                        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Keyboard shortcut map** (registered globally while queue is active):

| Key | Action |
|---|---|
| `A` | Accept — publish with model's primary + secondary |
| `E` | Edit — open node picker to select primary |
| `S` | Add Secondary — open node picker for secondary tag |
| `N` | None Fits — no node applies |
| `X` | Exclude — non-gradable / case stem / irrelevant |
| `U` | Undo last decision |
| `→` or `L` | Skip to next (no decision) |
| `←` or `H` | Go back to previous |
| `?` | Toggle keyboard help overlay |
| `Esc` | Close any open modal/picker |

**Decision timing**: `seconds_spent` is auto-computed from when the unit first becomes visible to when the decision fires. Pauses if the window loses focus.

**Bucket colour coding**:
- Unit header background tinted faintly in bucket colour (A = dark green, B = dark amber, C = dark red, D = dark grey).
- The bucket badge in the top-right is always prominent.

**Queue preview**: Shows next 3 items with their bucket, doc metadata, and a one-line evidence summary. Clicking any preview item jumps to it directly.

**Data contracts**:
```typescript
GET /api/v1/curate/queue?paper=P1&bucket=A&doc_type=suggested_answer&limit=50
→ QueueItem[] {
    unit_id: number
    display_label: string
    attempt_id: string
    attempt_label: string
    paper_id: string
    doc_type_id: string
    marks: number | null
    page_start: number
    page_end: number
    question_text: string       // CURATOR ONLY — never in student API
    answer_text: string | null  // CURATOR ONLY
    primary_suggestion: TagSuggestion
    secondary_suggestions: TagSuggestion[]
    bucket: "A" | "B" | "C" | "D"
    method: string
    gist: string
    evidence: {
      anchors: AnchorMatch[]
      run1_node_id: string
      run2_node_id: string
      run3_node_id: string | null
      agreement: "consensus" | "conflict" | "tiebreak"
      justification: string
      alternatives: string[]
    }
  }

POST /api/v1/curate/units/:unitId/decision
body: {
  action: "accept" | "accept_alt" | "edit" | "none_fits" | "exclude"
  primary_node_id?: string
  secondary_node_ids?: string[]
  gist?: string
  seconds_spent: number
}
→ DecisionResult { action, appearance_id?: number, decided_at: string }

POST /api/v1/curate/units/:unitId/undo
→ { success: boolean, reverted_action: string }
```

---

### 4.4 Node Picker (Edit flow)

Opens as a modal, keyboard-navigable, searches as you type.

```
┌──────────────────────────────────────────────────────────────────┐
│  Select primary node                                              │
│  ─────────────────────────────────────────────────────────────   │
│  [🔍 Type to search...                                        ]   │
│                                                                    │
│  P1 — Financial Reporting                                         │
│    ▼ Ind AS (Standards)                                           │
│       ● Ind AS 115 — Revenue Recognition    [●●●●●]  ← Suggested │
│         Ind AS 116 — Leases                 [●●●○○]              │
│         Ind AS 103 — Business Combinations  [●●●●○]              │
│    ▶ Companies Act provisions                                      │
│    ▶ Standards on Auditing (cross-reference)                      │
│  P2 — Advanced Financial Management                               │
│    ▶ …                                                            │
│                                                                    │
│  ─────────────────────────────────────────────────────────────   │
│  [↑↓ Navigate]  [Enter: Select]  [Esc: Cancel]                   │
└──────────────────────────────────────────────────────────────────┘
```

- Search filters the tree live. Results show matching nodes with their path.
- The suggested node is highlighted and pre-focused.
- Arrow keys navigate. Enter selects. Escape cancels.
- Search uses `GET /api/v1/taxonomy/nodes?q=...&paper=P1` — returns matching nodes sorted by importance.

---

### 4.5 Bulk Accept (`/bulk`)

```
┌──────────────────────────────────────────────────────────────────┐
│  Bulk Accept — Bucket A                                           │
│  ─────────────────────────────────────────────────────────────   │
│  Document: CA Final Nov 2024 — P1 Suggested Answer               │
│  Bucket A units ready: 18                                         │
│                                                                    │
│  SAMPLE (5 of 18):                                                │
│  Q1(a) → Ind AS 115  ●●●●●  "Revenue from bundled contract…"    │
│  Q2(b) → Ind AS 116  ●●●○○  "Lease modification — lessee…"      │
│  Q3    → Sec 149     ●●●●○  "Independent director quorum…"      │
│  Q4(a) → SA 700      ●●●●○  "Modified opinion trigger…"         │
│  Q5(b) → Sec 44AB    ●●●○○  "Tax audit threshold FY 2025…"      │
│                                                                    │
│  [✓ Accept All 18 Bucket A Units]    [Review one by one →]       │
│                                                                    │
│  ─────────────────────────────────────────────────────────────   │
│  ALL DOCUMENTS                                                     │
│  ─────────────────────────────────────────────────────────────   │
│  Nov 2024 P1 SA  →  18 Bucket A ready  [Accept all]              │
│  Nov 2024 P2 SA  →  14 Bucket A ready  [Accept all]              │
│  May 2024 P1 SA  →   9 Bucket A ready  [Accept all]  ← different │
└──────────────────────────────────────────────────────────────────┘
```

**Data contract**:
```typescript
POST /api/v1/curate/documents/:docId/bulk_accept_bucket_a
→ { accepted_count: number, skipped_count: number }
```

---

### 4.6 Document Catalogue (`/documents`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Documents          [Filter ▼]  [Status ▼]  [Attempt ▼]  [+ Import]  │
│  ─────────────────────────────────────────────────────────────────── │
│                                                                        │
│  Document                  Paper  Attempt  Type  Catalog     Extract  │
│  ─────────────────────────────────────────────────────────────────── │
│  CA Final Nov 2024 P1 SA   P1     2024-11  SA    ✓ confirmed  ✓ done │
│  CA Final Nov 2024 P1 QP   P1     2024-11  QP    ✓ confirmed  ✓ done │
│  CA Final May 2024 P2 SA   P2     2024-05  SA    ⚠ needs rev  ✓ done │
│  RTP Nov 2024 P3            P3     2024-11  RTP   ✓ confirmed  ⟳ run  │
│  RTP May 2024 P1            P1     2024-05  RTP   ○ inferred   ○ pend │
│                                                                        │
│  [Load more]                                Total: 47 documents        │
└──────────────────────────────────────────────────────────────────────┘
```

**Document detail** (`/documents/:docId`):
- Metadata header: SHA256, blob path, attempt, paper, doc type, series, catalog status, extract status.
- Unit list: table with `label_path`, `marks`, `kind`, `classify_status`, `parse_confidence`.
- Actions: Confirm metadata, Reject, Re-extract (⚠ destructive — confirmation required), View PDF blob link.
- Re-extract shows a warning: "This will re-run L2 extraction. Existing units will be marked non-current. Proceed?"

**Data contracts**:
```typescript
GET /api/v1/documents?paper=P1&catalog_status=confirmed&limit=50
→ DocumentListResponse {
    documents: DocumentSummary[]
    total: number
  }

GET /api/v1/documents/:docId
→ DocumentDetail {
    document: Document
    units: UnitSummary[] {
      id, label_path, display_label, marks, kind
      classify_status, parse_confidence, current
    }
  }

POST /api/v1/curate/documents/:docId/confirm
body: { paper_id?, doc_type_id?, attempt_id?, series? }
→ { catalog_status: "confirmed" }

POST /api/v1/curate/documents/:docId/reject
→ { catalog_status: "rejected" }
```

---

### 4.7 Taxonomy Browser (`/taxonomy`)

**Purpose**: Browse the full node tree. Edit descriptors. Approve or revise LLM-drafted descriptions.

**Layout**: Two-pane. Left: tree navigator. Right: descriptor editor.

```
┌──────────────────────────────────────────────────────────────────┐
│  Taxonomy                    [Paper: All ▼]   [Filter: Unapproved]│
│  ────────────────────────────────────────────────────────────     │
│  TREE                        │  EDITING: P1-P425DG               │
│  ──────────────────────      │  ──────────────────────────────── │
│  P1 — Financial Reporting    │  Ind AS 115 — Revenue Recognition  │
│   ▼ Ch 1: Ind AS             │  Level: subtopic                   │
│     ▼ Ind AS standards       │  Paper: P1                         │
│       ● Ind AS 115  ✓ appr  │  Parent: Ind AS (standards) topic  │
│         Ind AS 116  ✓ appr  │                                     │
│         Ind AS 103  ✗ draft │  DESCRIPTOR                        │
│   ▼ Ch 2: Companies Act      │  ┌──────────────────────────────┐ │
│     ▶ Directors              │  │ [Description text area      ] │ │
│     ▶ Mergers                │  │  ≤ 40 words                   │ │
│   ▶ Ch 3: Audit Standards    │  └──────────────────────────────┘ │
│                              │                                     │
│  P2 — Adv. Financial Mgmt   │  Keywords                          │
│   ▶ Ch 1: Capital Structure  │  [revenue recognition] [×]         │
│                              │  [performance obligation] [×]      │
│                              │  [+ Add keyword]                   │
│                              │                                     │
│                              │  Source: llm_draft  ✗ Unapproved  │
│                              │  [✓ Approve]   [Save Changes]      │
└──────────────────────────────────────────────────────────────────┘
```

**Data contracts**:
```typescript
GET /api/v1/taxonomy/nodes?paper=P1&approved=false
→ NodeHierarchyResponse

PUT /api/v1/taxonomy/nodes/:nodeId/descriptor
body: { description: string, keywords: string[], approved: boolean }
→ Descriptor
```

---

### 4.8 System Health (`/system`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  System Health                         ● HEALTHY  20:15 IST          │
│  ─────────────────────────────────────────────────────────────────── │
│                                                                        │
│  ALARMS                                                                │
│  ✓ BACKUP_STALE          Last backup: 3h ago (caf_20260926.dump)     │
│  ✓ ZERO_LINKS_DISCOVERED  Last run: 2024-11-01 · 47 new links         │
│  ✓ EXTRACTION_FAILURE     Failure rate: 2.1%  (< 20% threshold)      │
│  ✓ BUDGET_CAP_REACHED     No budget aborts in last 30 runs            │
│  ✓ BUCKET_A_PRECISION     Precision: 87.3%  (≥ 80% threshold)        │
│                                                                        │
│  MODEL EVALUATION                                                      │
│  ─────────────────────────────────────────────────────────────────── │
│  Bucket  Samples  Agreed  Precision                                   │
│   A        423     387     91.5%  ●●●●●                              │
│   B         47      31     66.0%  ●●●○○                              │
│   C         23      12     52.2%  ●●○○○                              │
│  Gate: ✓ PASSED  (Bucket A >= 80%)                                    │
│                                                                        │
│  RECENT PIPELINE RUNS                                     [Refresh]   │
│  ─────────────────────────────────────────────────────────────────── │
│  ⟳ l3_classify    running  47/120 units   started 19:53  IST         │
│  ✓ l2_extract     done     3 docs         18:42  IST                 │
│  ✓ l1_fetch       done     12 files       17:15  IST                 │
│  ✗ l1_discover    failed   src: icai-bos  16:02  IST    [View log]   │
│                                                                        │
│  BACKUPS                                                               │
│  ─────────────────────────────────────────────────────────────────── │
│  caf_20260926_200000.dump   486 MB   3h ago   [Verify restore]        │
│  caf_20260925_200000.dump   481 MB   27h ago  ✓ verified Sep 25       │
│  [Run backup now]                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**UX details**:
- Alarm rows refresh every 60s via SWR. A row flashes briefly on status change.
- Recent runs use SSE (Server-Sent Events) for live progress: `GET /api/v1/system/runs/stream`.
- "Verify restore" triggers `POST /api/v1/system/backups/:filename/verify` and shows the result inline.

**Data contracts**:
```typescript
GET /api/v1/system/health
→ SystemHealthResponse {
    status: "OK" | "WARNING" | "CRITICAL"
    evaluated_at: string
    alarms: Alarm[] {
      code: string
      level: "info" | "warn" | "error" | "alarm"
      message: string
      triggered: boolean
    }
  }

GET /api/v1/system/runs?limit=10
→ RunSummary[] {
    id, stage, status, started_at, finished_at
    stats: Record<string, number>
    error: string | null
  }

GET /api/v1/system/model-evaluation
→ ModelEvaluationResponse {
    total_reviewed: number
    top1_agreement: number
    bucket_metrics: Record<"A"|"B"|"C"|"D", BucketMetric>
    passed: boolean
  }

GET /api/v1/system/backups
→ BackupListResponse {
    backups: { filename, size_bytes, created_at, verified: boolean, verify_result?: string }[]
  }

POST /api/v1/system/backups
→ { filename: string, created_at: string }

POST /api/v1/system/backups/:filename/verify
→ { success: boolean, table_counts: Record<string, number>, note: string }
```

---

## 5. API Layer Design

### 5.1 Principles

1. **Student APIs never return `question_text` or `answer_text`** (Decision D2 — enforced at backend, at Zod schema level in the client, and at TypeScript type level).
2. **Curator APIs require `X-Curator-Token` header** — a single shared secret from `.env`. No JWT, no user management for Phase 1.
3. **All timestamps in ISO 8601 with timezone** (always UTC from backend; displayed in Asia/Kolkata in the UI).
4. **Node IDs are opaque strings** — never decompose in the UI.
5. **Pagination**: `?limit=N&offset=M` on all list endpoints.
6. **Student API is read-mostly** — only `PUT /progress`, `PUT /notes`, `POST /revision/:nodeId/outcome`, and mock test CRUD mutate state.

### 5.2 Complete API Surface

#### Student API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/dashboard` | Dashboard summary |
| `GET` | `/api/v1/papers` | Papers list with scores |
| `GET` | `/api/v1/papers/:paperId/tree` | Full tree with importance |
| `GET` | `/api/v1/subtopics/:nodeId` | Subtopic detail |
| `PUT` | `/api/v1/subtopics/:nodeId/progress` | Update progress status |
| `PUT` | `/api/v1/subtopics/:nodeId/notes` | Save notes |
| `GET` | `/api/v1/plan?hours=N&days=N&papers=...` | Study plan |
| `GET` | `/api/v1/revision/due` | Revision due list |
| `POST` | `/api/v1/revision/:nodeId/outcome` | Record revision outcome |
| `GET` | `/api/v1/mock-tests` | Mock test history |
| `POST` | `/api/v1/mock-tests` | Log a mock test score |
| `DELETE` | `/api/v1/mock-tests/:id` | Delete a mock test entry |
| `GET` | `/api/v1/why/subtopic/:nodeId` | Score explainability |
| `GET` | `/api/v1/meta` | Attempt list, scheme, last recompute |

#### Curator API (X-Curator-Token required)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/curate/queue` | Annotation queue |
| `GET` | `/api/v1/curate/units/:unitId` | Full unit detail |
| `POST` | `/api/v1/curate/units/:unitId/decision` | Submit decision |
| `POST` | `/api/v1/curate/units/:unitId/undo` | Undo decision |
| `POST` | `/api/v1/curate/documents/:docId/bulk_accept_bucket_a` | Bulk accept |
| `POST` | `/api/v1/curate/documents/:docId/confirm` | Confirm catalogue metadata |
| `POST` | `/api/v1/curate/documents/:docId/reject` | Reject document |
| `GET` | `/api/v1/documents` | Document catalogue |
| `GET` | `/api/v1/documents/:docId` | Document detail |
| `GET` | `/api/v1/taxonomy/nodes` | Taxonomy hierarchy |
| `GET` | `/api/v1/taxonomy/nodes/search?q=...` | Node search |
| `PUT` | `/api/v1/taxonomy/nodes/:nodeId/descriptor` | Update descriptor |
| `POST` | `/api/v1/curate/intel/recompute` | Trigger intel recompute |
| `GET` | `/api/v1/system/health` | System health + alarms |
| `GET` | `/api/v1/system/runs` | Pipeline run history |
| `GET` | `/api/v1/system/backups` | Backup list |
| `POST` | `/api/v1/system/backups` | Trigger backup |
| `POST` | `/api/v1/system/backups/:filename/verify` | Verify a backup |
| `GET` | `/api/v1/system/model-evaluation` | Model evaluation report |

### 5.3 Type Generation Pipeline

```bash
# Run after backend starts — part of dev setup
curl http://localhost:8000/openapi.json > web/packages/api-client/openapi.json
npx openapi-typescript web/packages/api-client/openapi.json \
  --output web/packages/api-client/src/generated.ts

# Uses openapi-fetch for type-safe fetch calls:
import createClient from "openapi-fetch"
import type { paths } from "./generated"

const client = createClient<paths>({ baseUrl: "http://localhost:8000" })
const { data } = await client.GET("/api/v1/dashboard")
```

### 5.4 D2 Compliance at Type Level

```typescript
// packages/api-client/src/schemas.ts

// Student subtopic appearance — no question or answer text
export const AppearanceSummarySchema = z.object({
  attempt_id: z.string(),
  attempt_label: z.string(),
  doc_type_id: z.string(),
  display_label: z.string(),
  marks: z.number().nullable(),
  law_stale: z.boolean(),
  signal_class: z.enum(["exam", "practice"]),
  // NO question_text, NO answer_text
})

// Curator queue item — has question and answer text
export const QueueItemSchema = z.object({
  unit_id: z.number(),
  display_label: z.string(),
  attempt_id: z.string(),
  paper_id: z.string(),
  doc_type_id: z.string(),
  marks: z.number().nullable(),
  question_text: z.string(),        // CURATOR ONLY
  answer_text: z.string().nullable(), // CURATOR ONLY
  bucket: z.enum(["A", "B", "C", "D"]),
  gist: z.string(),
  // ...
})
```

### 5.5 Runtime Zod Validation

```typescript
// All API responses validated at boundary — throws in development, logs in production
import { SubtopicDetailSchema } from "@ca-study/api-client"

async function fetchSubtopic(nodeId: string) {
  const res = await fetch(`/api/v1/subtopics/${nodeId}`)
  const json = await res.json()
  return SubtopicDetailSchema.parse(json) // ZodError if shape is wrong
}
```

---

## 6. FastAPI Static File Serving

The Vite build outputs to `dist/`. FastAPI serves it:

```python
# packages/api/caf_api/main.py
from fastapi.staticfiles import StaticFiles
import os

STUDENT_DIST = os.environ.get("STUDENT_DIST", "web/apps/student/dist")
CURATOR_DIST = os.environ.get("CURATOR_DIST", "web/apps/curator/dist")

# Mount curator app at /curator (internal, not exposed to students)
app.mount("/curator", StaticFiles(directory=CURATOR_DIST, html=True), name="curator")

# Mount student app at root — catch-all for SPA routing
app.mount("/", StaticFiles(directory=STUDENT_DIST, html=True), name="student")
```

**Development**: Both Vite dev servers run independently (`pnpm --filter student dev` on :3000, `pnpm --filter curator dev` on :3001). FastAPI runs on :8000. Vite proxies `/api/*` to `:8000`.

---

## 7. Demo Mode

For testing without real data:

```typescript
// apps/student/src/lib/demo.ts
// Activated by ?demo=true query param or VITE_DEMO_MODE=true env var

export const isDemoMode = () =>
  new URLSearchParams(window.location.search).get("demo") === "true" ||
  import.meta.env.VITE_DEMO_MODE === "true"

// All API hooks check isDemoMode() and return fixture data instead of fetching
```

Demo fixtures in `apps/student/src/fixtures/`:
- `dashboard.json` — realistic dashboard with 58% coverage, 3 due for revision, 14-day streak
- `papers.json` — all 6 papers with realistic coverage and importance scores
- `plan.json` — 3-day study plan
- `revision.json` — 3 due items

---

## 8. Implementation Phases

### Phase 1 — Foundation (1 week)
- Turborepo setup: `apps/student`, `apps/curator`, `packages/api-client`, `packages/ts-config`
- Vite + React + TypeScript scaffolding for both apps
- OpenAPI type generation pipeline
- Shared Zod schema package
- FastAPI CORS + static file serving + `X-Curator-Token` middleware

### Phase 2 — Student App Core (2 weeks)
- Design tokens (Tailwind config), colour system, typography
- Dashboard
- Papers overview with progress rings
- Paper detail with two-pane tree + importance sort
- Subtopic detail panel — status toggle, why breakdown, appearances
- Progress tracking (optimistic updates)
- Dark mode toggle

### Phase 3 — Student App Study Features (1 week)
- Notes editor (Tiptap integration)
- Study plan view
- Revision queue (single-card mode)
- Progress overview accordion
- Mock test log

### Phase 4 — Student App Polish (1 week)
- Mobile responsive layout + bottom nav
- Progress celebration animations (confetti on chapter complete)
- Streak counter
- Skeleton loaders for every route
- PWA manifest + service worker
- Demo mode fixtures

### Phase 5 — Curator Workbench (2 weeks)
- Dark theme design tokens
- Queue workbench with keyboard shortcuts
- Node picker modal (search + hierarchy)
- Bulk accept view
- Document catalogue + detail

### Phase 6 — Curator Tools (1 week)
- Taxonomy browser + descriptor editor
- System health + alarms
- Pipeline run monitor (SSE)
- Backup management

### Phase 7 — Hardening (1 week)
- Playwright E2E tests for both apps
- OpenAPI drift detection in CI
- D2 compliance automated checks
- Accessibility audit (WCAG 2.1 AA target)
- Load testing (the student app should handle the small user base with no perceptible lag)

---

## 9. Accessibility

- **Target**: WCAG 2.1 Level AA
- All interactive elements have visible focus rings (custom `focus-visible:ring-2 ring-indigo-500`)
- Progress bars use `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and a text alternative
- Importance dots have `title` attributes with numeric scores
- The revision queue card is navigable with keyboard only (no mouse required)
- Curator keyboard shortcuts are documented in an accessible help overlay (`?`)
- All icons paired with visible or screen-reader text labels

---

## 10. Performance Targets

| Metric | Student App Target | Notes |
|---|---|---|
| First Contentful Paint | < 1.0s (4G) | Vite code-splits per route |
| Time to Interactive | < 2.0s (4G) | Dashboard is the hot path |
| Largest Contentful Paint | < 2.5s | Paper tree with 264 nodes |
| API response: `/dashboard` | < 150ms | Pre-aggregated in intel schema |
| API response: `/papers/:id/tree` | < 80ms | Flat query, no N+1 |
| Bundle size (student) | < 400KB gzipped | Tiptap is the biggest risk |
| Bundle size (curator) | < 250KB gzipped | No rich text |

**Strategies**:
- Route-level code splitting (automatic with React Router v6 lazy routes)
- TanStack Query caching with `staleTime` tuned per route
- Tree data fetched in full (264 nodes is small — no lazy loading of tree branches)
- Tiptap loaded lazily only when the notes editor is in view
- Recharts loaded lazily only on `/mock` and `/progress`
