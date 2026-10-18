# Stitch UI redesign verification

2026-10-17 record. Subsequent checks on 18 October resolved the browser startup
blocker and verified the reader zoom correction in Chromium and WebKit. See the
[latest application checkpoint](Application_checkpoint_2026_10_18.md) for current
results. The original findings below are retained as historical context; automated
captures do not constitute full manual approval of every route and state.

## Changes

- Shared forest palette and matching light theme, locally bundled Source Sans 3/Newsreader with licences, 16px interface text, larger reader text, readable metadata and editorial headings.
- Dark default for missing/invalid preferences; explicit Light/Dark/System persistence, OS following only for System, cross-tab events and pre-paint appearance in both HTML entrypoints.
- CA Study Companion shell, 1024px sidebar breakpoint, tablet drawers, mobile study navigation, account disclosure and collapsed legacy History. Administrator links remain capability gated.
- Compact Today hierarchy; disclosed question filters and result rows; 1280px syllabus detail breakpoint; continuous reader with on-demand outline/topics, topic-owned notes and visible classification limitations.
- Paper grid breakpoints, preference grouping, revision grouping and separate progress evidence tab.
- Review queue opened on demand, 340px labels column, smaller-screen panes preserving mounted edits; extraction reading panes; mobile catalogue detail rows; focused invitation and access confirmation dialogs; consistent legacy/admin surfaces.

The redesign does not introduce public API or database changes. Existing unrelated uncommitted work was preserved, including prior changes in overlapping reader/review files. Production builds regenerate tracked distribution assets.

## Passed checks

| Check | Result / evidence |
| --- | --- |
| Workspace and browser TypeScript | Passed: [type-check.txt](stitch-review/type-check.txt), [browser-type-check.txt](stitch-review/browser-type-check.txt) |
| Both production builds | Passed: [build.txt](stitch-review/build.txt) |
| Theme and contrast checks | 25 passed: [theme-tests.txt](stitch-review/theme-tests.txt) |
| Isolated runtime HTTP smoke | 22 HTML routes and six study API endpoints returned 200: [http-smoke.json](stitch-review/http-smoke.json) |
| Scoped whitespace/diff checks | Passed |

The theme checks evaluate the actual HTML bootstrap and transpiled theme hook with event/storage stubs. They cover absent/invalid preferences on both OS appearances, storage failure, explicit choices and theme events. They are not browser paint measurements.

All primary, secondary, accent, warning and error text tokens meet 4.5:1 against canvas, surface and raised surface in both themes. Accent button text also meets 4.5:1. This measures token pairs, not every rendered pixel or custom content asset.

## Browser blocker and remaining acceptance

The owned PostgreSQL/browser harness started successfully on web port 8877 with fixed database port 5442 after Colima failed to forward a random port. No normal database was used.

Headless Chromium failed before creating a page with a macOS Mach-port bootstrap error. WebKit aborted before creating a page. Full Chromium also aborted. The computer-use fallback returned no available browser and a service startup failure. Details: [browser-startup.md](stitch-review/browser-startup.md).

Consequently browser interaction regressions, viewport/full-page screenshots, visual corrections, contact sheet and manual route/state inspection remain incomplete. Builds and HTTP checks do not replace them. The [route/state log](stitch-review/review-log.md) explicitly records pending coverage. Existing screenshot evidence from prior phases is not evidence for this redesign.

The capture suite covers both engines, desktop/mobile dark and light, intermediate widths, reader answer/source states and overflow assertions. Additional existing suites cover note failures/navigation protection, syllabus keyboard navigation, filters/return state, reviewer drafts, counts/disputes, account isolation and permissions. These must run successfully once browser startup is available.

## Data limitations retained

`GET /revision/due` returns only due revisions. The UI shows Overdue and Due today from that response; it does not fabricate an upcoming queue. Detailed importance calculations remain on each topic, linked from Progress. No timers, bookmarks, session tracking, examiner commentary or question-note storage were introduced.

## Specification

[Updated UI specification](UI_System_Design_and_Implementation_Plan.md) supersedes conflicting Phase 7 styling. The exported dark Today PNG was inspected as a palette/hierarchy reference; it is not a screenshot of the implemented app.
