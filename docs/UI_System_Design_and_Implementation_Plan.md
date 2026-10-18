# Study workspace — Stitch redesign (October 2026)

This specification supersedes the previous single-user, desktop-only curator, divergent branding and gamification design. Phase 6 mechanisms remain authoritative. Hosting/deployment are Phase 8. UI completion and corpus readiness are separate acceptance gates.

## October 2026 redesign authority

This revision supersedes conflicting Phase 7 presentation guidance below. Preserve URLs, account isolation, review history, publication rules and API contracts. The ZIP supplies visual direction, not application data or static replacement screens.

- Dark forest surfaces, restrained green actions, editorial headings and readable sans-serif content. Dark action text is `#003822`.
- Brand: CA Study Companion. Compact account disclosure contains appearance, settings and sign out. Review shared content is a secondary destination; legacy review lives under History. Administrator destinations remain capability-gated.
- Desktop sidebar 224px from 1024px, header 64px and 32px gutters. Tablet drawer and 24px gutters; mobile 56px header, 16px gutters, safe-area-aware bottom navigation.
- Today: compact Continue studying, then three planned items beside revision and personal progress; recent activity follows. Detailed coverage belongs on Progress.
- Questions: search and Paper visible; remaining filters disclosed. Compact rows with two-line previews, answer state and Open question; full taxonomy paths on demand.
- Reader: continuous complete document, every sibling and OR choice retained. Answer, Source and Topics tools; inline complete available answer, source drawer, topic-owned notes. No question-note storage or automatic completion.
- Review: question and answer beside 340px labels above 1280px. Below, Question/Answer/Labels/Evidence panes preserve mounted edits. Queue opens on demand.
- All other student, review, administration, legacy and authentication routes inherit the same surfaces, typography, controls, responsive tables and accessible states. No fabricated scores, session metrics or examiner commentary.

Visual acceptance requires desktop/mobile dark and desktop light captures for every route, intermediate widths, browser engine coverage, dialog/state inspection and a review log. Build success alone is insufficient.

### Initial-review corrections (17 October 2026)

- Default the reader to original published source pages, retaining every recorded sibling/OR page and available answer. Load later pages near the viewport; allow enlargement and optional cropping. Mark the recorded question start where known. Keep extracted text available on demand. Boundaries and source pairing remain reviewable evidence, not guaranteed correct; keep full pages and a visible limitation notice as the default.
- Put raw mark issue identifiers, release IDs and hashes in Content details. Keep readable quality and applicability limitations beside the question.
- Default each account to English content. Profile → Preferences → Include Hindi questions explicitly opts into detected Hindi content. Apply the preference on the server to lists, search, question access and question-page access. Detection uses Devanagari text and Hindi-labelled sources; it is not a complete language classifier.
- Reuse study context only within an authenticated read request and its database transaction. Fetch only required evidence fields; defer reference trees and extracted-text code until needed. Keep private content out of persistent browser caches and clear in-memory client caches on account changes.
- Importance explanations preserve unknown attempt IDs as unavailable rather than rejecting the response or inventing an attempt.

Implementation evidence and outstanding visual limitations: [loading and reader review](loading-reader-review/VERIFICATION.md).

## Objective and actual starting state

The product is a study companion for official questions, available answers, textbook-derived syllabus navigation, historical evidence, deliberate personal progress and collaborative classification.

Required journeys: resume a topic/question; navigate the syllabus; find previous questions; read the complete question and reveal its answer; deliberately record progress/notes; return without losing selection; review shared content with source evidence.

Baseline commit `cfe1900`: 344 Python and 126 browser tests. Live corpus has no reviewed classification revisions, published question snapshots or approved attempt bindings. Luna suggestions are experimental. Taxonomy, source, extraction, pairing, inventory and prior reviews remain outstanding. Every screen supports this state and populated data. Demo fixtures are explicitly labelled, isolated from live records, and never replace failed requests.

## Fixed design system

Shared tokens live in `web/packages/workspace/tokens.css`; both existing React/Vite/Tailwind apps consume them. Share typed API contracts, not a new component framework or state library.

| Token | Light | Dark |
| --- | --- | --- |
| Canvas | `#F5F7F2` | `#101411` |
| Surface | `#FFFFFF` | `#191D1A` |
| Subtle surface | `#EBEFE9` | `#232A25` |
| Text | `#191D1A` | `#E0E3DE` |
| Secondary text | `#4F6055` | `#BEC9C0` |
| Border | `#CCD5CC` | `#3F4942` |
| Accent | `#226A43` | `#85D7AA` |
| Accent surface | `#DEEDDF` | `#203B2B` |
| Success text | `#17603A` | `#85D7AA` |
| Warning text | `#805000` | `#F8BB72` |
| Error text | `#B42318` | `#FFB4AB` |

Locally bundled Source Sans 3 for controls and content; Newsreader for page and major section headings. No runtime remote fonts. Body `16px/26px`; reader `18px/30px`, mobile reader `17px/28px`. Page title `32px/40px`, mobile `28px/36px`; metadata at least `14px/20px`. Counts, dates, scores and marks use tabular numerals.

Spacing: 4, 8, 12, 16, 24, 32, 48px. Panel radius 10px, control radius 8px, chips 6px. Panel padding 24px desktop/16px mobile. Controls minimum 40px, mobile targets 44px. Borders define sections; shadows only overlays/floating menus. Primary actions use accent; secondary surface/border; destructive error styling. Every status includes text. Focus is visible. Hover/focus transitions 120ms, overlays at most 160ms, respect reduced motion.

No confetti, fabricated streaks, decorative gradients, glowing panels, importance dots, repeated oversized metric cards, illustrations, decorative photography or generated artwork. Dark is the default for absent or invalid preferences, independent of OS. Preserve Light and Dark. Store System explicitly as `caf_theme=system`; follow OS changes only in System. Initialise in both HTML heads before first paint and synchronise tabs and workspaces.

Reusable patterns within each app: page header, filter bar, row, status label, empty state, error panel, content-shaped skeleton, dialog, drawer, disclosure. Page order: title/purpose → context/filters → main content → secondary evidence. IDs, hashes, jobs and raw JSON belong in Technical details.

## Student shell and state

Desktop ≥1024px: fixed 224px left navigation, sticky 64px header, 32px content padding, normal content maximum 1200px. Primary navigation Today, Papers, Syllabus, Questions, Plan, Revision; secondary Progress, Mock results. Bottom area profile/settings, theme, sign out, Review shared content. Header current attempt, selected-paper summary and labelled Search questions.

Tablet 768–1023px: navigation drawer; header page title/attempt/search; 24px padding. Mobile <768px: 56px header; bottom Today, Syllabus, Questions, Plan, More; More labelled sheet has remaining destinations; 16px content padding with bottom/safe-area allowance. Critical actions have text labels.

Keep existing URLs. `/syllabus` is primary; `/textbooks` redirects to corresponding draft syllabus preview retaining query selection. Old paper/topic links remain valid.

Filters, paper/node, pagination, active tabs are URL parameters. Account-scoped session storage preserves tree expansion, scroll/focus and last valid destination. Resume is device-local navigation, never measured study time. Returning from reader restores originating filters/selection/scroll/focus. Account changes cancel requests, clear cached private content and discard another account's navigation. Attempt changes invalidate context-dependent data; preserve only destinations verified valid. Maintain note-save serialization and draft protection.

## Student screens

### Today

Two columns desktop 2fr/1fr, stacked mobile. Header Today with target context.

Main order: Continue studying (one horizontal panel, last valid title/paper/breadcrumb, Continue; otherwise Start with your syllabus); Next in your plan (up to three server-ordered items, topic/paper/minutes/actual reason/Open topic, Syllabus-based or Historically ranked); Revision due (up to five, due date/overdue duration/Start revision; empty Nothing is due for revision).

Secondary: personal progress single horizontal bar completed/total; reviewed-question count/Browse questions; small Content readiness/View coverage; last five actual progress/revision events. No empty weak-topic panel or corpus matrix. Missing binding produces one contextual notice: “The syllabus for this attempt is awaiting review.” Actions Preview draft syllabus and View readiness. Opening content never means studied.

### Papers

Separate Group 1/Group 2 sections; desktop three panels/row, tablet two, mobile one. Each: code/official name/completed-total/one bar; reviewed question availability/revision due; primary Open syllabus, secondary Browse questions. Unknown displays Not available, never zero. No headline average importance. Group and Sort filters; sorts Paper order, Least completed, Most revisions due.

### Syllabus and topic

Desktop tree 300px independently scrollable, detail remaining space. Below1280 full-width tree; opening a node replaces tree with detail and Back to syllabus. Toolbar paper/search/status All, Not started, In progress, Done; Expand to topics, Collapse all.

Use actual hierarchy including chapter/unit levels, without fixed module counts. Containers toggle; eligible subtopics open detail. Indent20px/level, row≥40px, selected accent surface/left rule. Search retains ancestors and temporarily expands matching paths; clearing restores prior expansion. Status filters apply to leaves retaining ancestors. Tree keyboard navigation/semantics: Up/Down, Home/End, Left/Right, Enter/Space.

Topic full breadcrumb/title/status selector Not started/In progress/Done. URL tabs Questions, My notes, Importance, Textbook references.

Questions: attempt/collection/source family/question label/relevant part/marks/answer availability; link complete question; deduplicate repeated part appearances; distinguish no filters match from no published questions.

My notes: existing plain-text/Markdown Write/Preview and Save. Persistent Unsaved/Saving/Saved/Save failed state; failed saves retain draft and Retry. Unsaved navigation dialog Stay, Save and leave, Discard and leave; failed save stays. Keep existing note ordering, including edits during pending saves.

Importance: full index or unavailable; fixed columns Component, Raw signal and unit, Normalized index, Weight, Contribution. Bound formula; normalized0–100, weights percentages, contributions index points; separate known subtotal when full unavailable. Frequency lists usable reviewed attempts; partial attempts under Additional evidence not used in ranking. Freshness and How this was calculated disclosure.

Textbook references: edition/applicability/fallback/source title/page links. Student reading separated from curator controls. Draft preview has persistent Draft—awaiting review label, no progress mutations or assumed approved applicability.

### Questions

Searchable list, full-width search. Filters Paper, Attempt/Collection, Source type, Answer availability, Topic searchable taxonomy picker (no raw ID input). 300ms debounce and cancel obsolete requests. Changes reset page; active chips/Clear filters; page size20. Rows label/title, paper, attempt/collection/source family, two-line preview, marks, answer state. Private results separate My notes section linking owning topic.

No matches: “No questions match these filters”, Clear filters. No publications: “Reviewed questions will appear here after publication”, Explore syllabus. No live demo insertion.

### Complete question reader

Desktop reading≤800px, outline/evidence240px, overall≤1120px. Below1280 outline/evidence drawers. Header: named origin Back → paper/attempt → label/title → compact source-family/marks/answer status.

Shared case first then ordered numbered parts, continuous editorial sections rather than nested cards. Major part spacing/subtle rules; selected part left accent and Selected part text. Siblings/shared case remain visible. Wide tables scroll locally. Images readable natural sizes/captions/enlarge modal. Preserve choice/OR structure beside parts.

Reveal answer after complete question, sticky toolbar links to it; inline full ordered answer/part labels. Partial notice persists. Missing: “No reviewed answer is available for this question.” Answer hidden on question change only. No correctness score or automatic progress mutation.

Right: part outline, Covers N subtopics with distinct full paths, Topic labels verified by N students, disputes, View source, Content details. Source drawer: source/page selectors, previous/next page, page image, Open PDF. Desktop min(720px,50vw), mobile full-screen; focus restored close. Revisions/hashes in Content details.

Source-adjacent reading takes the split-view/source context principle from [RemNote's reader](https://help.remnote.com/en/articles/6690975-learning-from-pdfs-and-files-with-the-remnote-reader). Scope is official content and existing personal notes only.

### Plan

Header Your study plan; summary basis/weekly budget/allocated/unused minutes. Collapsible Adjust plan hours/paper-group scope/block duration. Server order and allocations authoritative. Ordered list default; Week view presents same whole blocks over next seven calendar days, assigns next block to least-loaded day, ties earliest, preserves global order within each day. Label Suggested schedule; no server commitment/completion, never exceed returned allocation.

Rows title/breadcrumb/minutes/status/factual reason; Start topic, Continue only In progress. Missing reviewed syllabus links draft; missing historical scores with reviewed syllabus uses existing Syllabus-based plan.

### Revision

Desktop queue300px+active, mobile list/focused item. Rows due date/overdue duration. Active full path/relevant questions; Reveal my notes; Recall was okay/Needs another revision existing outcomes. Advance only on successful mutation; failure retains item. Previous/Next navigate without outcome. Due counts, no readiness scores.

### Progress, mock results, settings

Progress personal summary/per-paper rows; status links syllabus selection. Separate Question coverage tab. Existing authenticated export; weighted progress only with reviewed basis.

Mock results table Date/Paper/Marks scored/Maximum marks/Percentage/Notes. Labelled validated add dialog. Delete confirmation names result. Paper-specific trend only≥2 real records, no comparison of incompatible maxima.

Settings sections Profile, Exam target, Selected papers, Study budget, Revision intervals, Appearance, Export. Human names; official grouped paper checkboxes; explicit Save dirty/saving/saved/failed states; target readiness explanation by selector; shell sign out remains accessible.

## Curator workspace

Same tokens/typography, denser14px body. Primary Review questions, Extraction, Syllabus & descriptors. Admin Readiness, Source catalogue, Bulk review, Accounts, System. Legacy history secondary. Existing route aliases preserved; UI permissions assist, backend decides.

### Classification

≥1280: queue260px, complete question/answer≥440px, labels/evidence360px, resizable keyboard-adjustable separators, sticky final-review bar. Collapse shell sidebar where required to preserve panes. 768–1279 queue drawer and60/40 content-label split where readable. <768 full-width Queue/Question/Answer/Labels/Evidence tabs preserving edits and full confirmation; no mobile publication shortcut.

Queue selectors (no unlabelled technical IDs), rows paper/attempt/label/outcome/blocker. Complete shared case/all parts/full expandable answer/source adjacent or mobile dialog. Selecting part highlights/scrolls content and mapping.

Per part: label/outcome/full primary path/secondary paths; Change primary, Add secondary, None fits, Needs review, Exclude; plain-language evidence; confidence/alternatives/provenance disclosure. Outcome transitions remove incompatible labels per contract.

Publication shows current mapping/distinct reviewer count, Current/Proposed comparison; disputes preserve prior publication. Readiness blockers link exact source/taxonomy/extraction tasks.

Final bar requires evidence/reason and confirmation of complete question, available answer and every part. Publish reviewed labels when eligible; Save blind review only existing workflow; separate Verify current labels, Withdraw my verification, Submit correction, admin resolution. No experimental Save draft. 409 comparison dialog clears confirmation, no silent retry. Shortcuts Alt+J/K prev/next, Alt+Q/A/L pane focus, disabled in editable controls, none publish.

### Extraction

Same queue/content/evidence layout; document/candidate/current header. Tabs Question assembly, Answer pairing, Quality checks, Revision differences. Original pages/source spans opposite complete assembled root. Full answer candidates/page evidence. Corrections preserve revision and create successors. Quality identifies dimension/revision. Admin promotion before/after and readiness. Accepting labels never clears source warnings.

### Syllabus/descriptors

Reuse official hierarchy with curator evidence/actions. Selected node tabs Source references, Descriptor, Applicability, History; full official path before descriptor. Page preview accompanies heading/span review. Labelled definition/terminology/inclusions/exclusions/nearby distinctions. Approval exact descriptor revision; editing invalidates approval. Admin release approval/activation distinct with manifest/migration evidence.

### Readiness

`/curator/readiness`, admin only. Filters attempt/taxonomy/paper/source family/blocker type. Paper summary and task table Paper/Stage/Blocker/Evidence/Required role/Next action. Drawer source pages/previous decisions/exact affected records.

Dependency stages: textbook edition/source → heading taxonomy/descriptors → applicability/attempt binding → metadata/ranges → extraction/answer pairing → classification/publication → expected inventory/coverage → priors/scoring freshness.

Typed administrator APIs for summary and audited binding/inventory/prior edits reuse Phase6 models and invalidation. Server-derived actor; expected revision/hash, evidence, idempotency required. Derive completeness from reviews, never arbitrary UI complete flag. Bindings/priors approved source evidence; unknown inventory stays unknown; stale writes conflict. Update OpenAPI/shared clients/build artifacts.

## Corpus continuation and genuine review

After evidence screens: revisit P5 Jan2026 fallback/exact prescribed edition; reconcile IBS guidelines/supplements/May2027 applicability; repair Phase5 malformed roots (swallowed papers, answer fragments, missing cases, false gradable units); combined-paper ranges/document roles/metadata conflicts/confirmed Q&A pairs; acquire genuine missing mock/model artifacts through discovery/import; fill paper/profile fixture gaps as actual artifacts arrive; successor taxonomy/extraction drafts preserve frozen history; rerun affected classification; independent student-adjudicated evaluation before calibration claims; reviewed inventory/prior mappings before reliable components.

Automation prepares evidence/corrections. Source/quality/applicability/classification attestations record the actual authenticated reviewer. Never manufacture approvals. Unavailable artifact remains explicit missing-source task with retrieval attempts/next action.

## Implementation order and acceptance

1. Replace design specification with screen/state examples.
2. Tokens, shells, controls, navigation/state.
3. Representative Syllabus/topic, reader, classification first.
4. Their populated/empty/blocked/loading/error/mobile verification.
5. Remaining screens.
6. Audited readiness contracts/workflows.
7. Corpus investigation/repairs and authenticated decisions as reviewers supply them.
8. Verification report separating UI/corpus status.

Keep API behavior, personal isolation, revision checks and ordered saves. Lazy-load pages/heavy reader/chart modules; no framework/state-library replacement.

| State | Required behavior/example |
| --- | --- |
| Loading | Content-shaped skeleton, aria-busy; no fabricated counts |
| Refreshing | Existing rows remain; unobtrusive refreshing text |
| Error | Concise failure, Retry |
| Empty | Distinguish no data vs no matching filters, one action |
| Unavailable | Missing binding/evidence labelled; never numeric zero |
| Saving | Retain draft, disable duplicate action |
| Failed mutation | Retain edits/confirmation context, Retry |
| Disputed | Name scope, retain published mapping |
| Stale score | Computation time, refresh status |
| Permission denied | Required capability without private records |

Examples: Today with no binding shows one notice plus draft/readiness actions; question search with unpublished corpus contains no fixture rows; complete reader keeps selected part and siblings; partial answer remains labelled after reveal; student B verifying current labels increases distinct student count; successor mapping resets count; stale admin readiness hash opens conflict with current record rather than overwriting.

Verify390/768/1280/1440px, light/dark, Chromium/WebKit with isolated fixtures. Journeys: Today→syllabus→question→answer→source→back context; search/filter/pagination return; concurrent/failed notes and account/context changes; progress/plan/revision refresh; syllabus plan unavailable scores; complete/partial/missing answers, tables/cases/OR; first review/second verification/changed count; concurrent conflict/admin disputes; extraction correction/review/promotion/regeneration; readiness mutations/durable invalidation; keyboard tree/dialogs/reader/review; private notes/export isolation.

Inspect screenshots/runtime, focus/labels/status/contrast/reduced motion/200% zoom. Horizontal scrolling only tables/source canvases. TypeScript, production builds, browser tests, focused Python contracts/auth and full relevant regressions. Database history changes require migration and backup/restore rehearsal before live.

Deliver specification, both interfaces, readiness API/workflows/evidence continuation, synchronized OpenAPI/client/build, `docs/Phase7_Verification.md` with screenshots/journeys/remaining gates. UI complete only when every specified screen/state works without developer explanation. Corpus ready only when genuine reviewed sources/bindings/extraction/classifications/coverage/priors pass gates. Report human-review/unavailable-source dependencies.

Before Phase8 invite real students for navigation, reading, notes/progress and classification usability pilot. Record actual observations/fix failures. Automated agents cannot replace this acceptance.
