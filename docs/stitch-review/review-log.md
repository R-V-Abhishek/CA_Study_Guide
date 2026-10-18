# Route and state review log

2026-10-17. **Visual acceptance is blocked, not passed.** No redesigned route was opened in a functioning browser. No screenshot or contact sheet was generated. The table is the pending review inventory, not a claim of visual inspection.

Target matrix: every route at 1440×900 dark/light and 390×844 dark; the capture suite also includes mobile light. Major layouts additionally use 1280×800, 1024×768 and 768×1024. Both Chromium and WebKit are configured. Viewport and full-page images are required.

| Route / area | States to inspect | Visual status |
| --- | --- | --- |
| `/` | Continue, plan, revisions, progress, recent activity | Blocked: browser launch |
| `/papers` | Groups, counts, availability | Blocked: browser launch |
| `/papers/:paperId` | Paper syllabus | Blocked: browser launch |
| `/papers/:paperId/:nodeId` | Deep link and topic tabs | Blocked: browser launch |
| `/syllabus` | Tree, search, status, selection and mobile back | Blocked: browser launch |
| `/syllabus?preview=draft` | Draft/applicability limitations | Blocked: browser launch |
| `/textbooks` | Draft redirect and preserved selection | Blocked: browser launch |
| `/questions` | Filters, results, filtered-empty and notes search | Blocked: browser launch |
| `/questions/:questionId` | Complete/partial/missing answers, all parts, source, outline, topic notes | Blocked: browser launch |
| `/plan` | Allocation, ordered agenda and preserved optional week view | Blocked: browser launch |
| `/revision` | Overdue/due today, explicit outcomes | Blocked: browser launch |
| `/progress` | Personal, coverage and importance tabs | Blocked: browser launch |
| `/mock` | Empty, add result and results | Blocked: browser launch |
| `/profile` | Exam target, papers, preferences and save failure | Blocked: browser launch |
| `/curator` | Classification alias | Blocked: browser launch |
| `/curator/classifications` | Queue, question, answer, labels, evidence, correction draft, dispute, picker | Blocked: browser launch |
| `/curator/extraction` | Source, complete question, answer, quality review and promotion | Blocked: browser launch |
| `/curator/textbooks` | Syllabus, descriptors and draft states | Blocked: browser launch |
| `/curator/syllabus` | Syllabus alias | Blocked: browser launch |
| `/curator/taxonomy-release` | Sources, crosswalk, blockers and deliberate approval | Blocked: browser launch |
| `/curator/readiness` | Actionable gaps and evidence dialogs | Blocked: browser launch |
| `/curator/documents` | Catalogue filters, mobile details | Blocked: browser launch |
| `/curator/catalog` | Catalogue alias | Blocked: browser launch |
| `/curator/catalogue` | Catalogue alias | Blocked: browser launch |
| `/curator/bulk` | Scope, evidence, consequences and explicit submission | Blocked: browser launch |
| `/curator/accounts` | List, invitation and access confirmation | Blocked: browser launch |
| `/curator/system` | Service health, processing and recovery | Blocked: browser launch |
| `/curator/queue` | Legacy history | Blocked: browser launch |
| `/curator/taxonomy` | Legacy taxonomy | Blocked: browser launch |
| `Unmatched student/review paths` | Unavailable page | Blocked: browser launch |
| `Authentication` | Loading, sign in, disabled, invitation required and error | Blocked: browser launch |
| `Shared states` | Navigation drawer, account disclosure, source and confirmation dialogs | Blocked: browser launch |

The automated capture inventory is in `web/tests/browser/stitch-redesign.spec.ts`. Existing student, classification, extraction, auth and question suites cover additional interaction states. Screenshots must still be opened, inspected, corrected and recaptured before acceptance.

See [browser startup evidence](browser-startup.md). HTTP route delivery is recorded separately in [http-smoke.json](http-smoke.json); it does not verify rendered layout.
