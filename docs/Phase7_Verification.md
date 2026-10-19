# Phase 7 verification

Date: 10 October 2026. Baseline: `cfe1900`. Production deployment remains Phase 8.

## Scope and acceptance

The student and curator applications now share the specified light/dark tokens, system typography and responsive navigation. Page modules and Markdown readers load lazily. Existing URLs remain valid, with syllabus and source-catalogue aliases. Personal navigation is account/context scoped; notes retain their serialized saves and draft protection.

Readiness exposes dependency-ordered evidence tasks and audited administrator decisions for bindings, expected inventory and official priors. Actor identity is server-derived. Source revisions/hashes, evidence and idempotency receipts are required. Conflicts preserve edits and demand renewed comparison; reviewed completeness is derived from inputs. No database migration was introduced.

**Corpus readiness and human usability acceptance remain open.** Automated fixtures verify workflows; they do not create live approvals or represent invited students. See [corpus continuation](Phase7_Corpus_Continuation.md) and [pilot protocol](Phase7_Usability_Pilot.md).

## Verification results

TypeScript checks, production builds, API/client/asset synchronization, all **359 Python tests** and all **196 browser tests** passed. The final Python run took 111.85 seconds; the complete Chromium/WebKit run took 5.2 minutes. All browser tests use an owned disposable PostgreSQL sandbox and cookie-backed fixture identities, with no live records modified.

```sh
pnpm --dir web type-check
pnpm --dir web build
uv run pytest
uv run scripts/phase7_verify_contracts.py
CAF_BROWSER_PORT=8786 uv run scripts/browser_server.py
CAF_BROWSER_PORT=8786 CAF_BROWSER_EXTERNAL=1 pnpm --dir web exec playwright test
```

Port 8786 was selected because an unrelated existing service occupied the default loopback port. The existing service was preserved. The normal Playwright command still manages its own harness/build; `CAF_BROWSER_EXTERNAL=1` permits an explicitly owned harness during iteration.

| Journey / state | Evidence |
| --- | --- |
| Today → syllabus → complete reader → answer → original source → back | `phase7-workspace.spec.ts`, `questions.spec.ts`, `verification.spec.ts`; URL selection, keyboard tree navigation and source focus return |
| Search/filter/pagination, private notes and return context | `questions.spec.ts`, `auth.spec.ts`; authenticated account isolation and private export |
| Notes edited during a pending save; failure, retry, account change and unsaved navigation | `student.spec.ts`, `auth.spec.ts`; newer drafts survive old acknowledgements, failed save stays on page |
| Progress, plan refresh and revision outcomes | `student.spec.ts`; server order/allocation, syllabus-based fallback, failed mutation retention and successful-only advancement |
| Complete, partial and missing answers; long cases, OR structure and wide tables | `questions.spec.ts`; siblings retained, answer reset on question change, table scroll contained locally |
| Review, verification, changed revision, disputes and stale publication conflict | classification API/publication tests and `classification.spec.ts`; independent review evidence and renewed confirmation |
| Extraction correction, answer resolution, quality and promotion | extraction/publication/recovery Python tests and `extraction.spec.ts`; complete pages, revision comparison, audited successor preservation, strict grading-role edits and retained evidence after stale failures |
| Binding/inventory/prior edits and durable score invalidation | `test_phase7_readiness.py`, `readiness.spec.ts`; reviewed source references, unknown inventory, stale hashes and concurrent idempotent receipts |
| Exact affected record beyond the first queue page | `test_phase5_api.py`, `classification.spec.ts`; filtering precedes pagination |
| Loading, refreshing, empty, unavailable, errors and permission denial | student/curator/readiness/taxonomy browser cases; no fabricated corpus or private fallback data |
| Responsive accessibility | 390, 768, 1280 and 1440px; light/dark; Chromium/WebKit; tree/pane keyboard controls, dialogs, reduced motion and 200% rendering zoom |

## Visual inspection

Screenshots use explicitly synthetic isolated fixtures. They are not live corpus readiness evidence. Actual PNGs were inspected for typography, hierarchy, theme, responsive layout, overlap and horizontal overflow. The run caught and corrected the long official-paper selector overflowing mobile, the mobile review footer covering labels, Safari dialog focus return and duplicate conflict announcements during render transitions.

| Screen | Mobile light / dark | Desktop light / dark |
| --- | --- | --- |
| Today | [light](phase7-screenshots/today-390-light.png) / [dark](phase7-screenshots/today-390-dark.png) | [light](phase7-screenshots/today-1440-light.png) / [dark](phase7-screenshots/today-1440-dark.png) |
| Syllabus / topic | [light](phase7-screenshots/syllabus-390-light.png) / [dark](phase7-screenshots/syllabus-390-dark.png) | [light](phase7-screenshots/syllabus-1440-light.png) / [dark](phase7-screenshots/syllabus-1440-dark.png) |
| Complete reader | [light](phase7-screenshots/reader-390-light.png) / [dark](phase7-screenshots/reader-390-dark.png) | [light](phase7-screenshots/reader-1440-light.png) / [dark](phase7-screenshots/reader-1440-dark.png) |
| Classification | [light](phase7-screenshots/classification-390-light.png) / [dark](phase7-screenshots/classification-390-dark.png) | [light](phase7-screenshots/classification-1440-light.png) / [dark](phase7-screenshots/classification-1440-dark.png) |

[Build verification](Phase7_Build_Verification.json) records the common application build identity `e2f7656-d9f215b722bd`, OpenAPI equality with the application, typed-client hashes and all referenced lazy assets. Both browsers also passed the final rebuilt production-identity check. Production chunks remain below the prior 500kB bundle advisory.

## Remaining gates

- Live inspection found zero reviewed classifications/publications/bindings/priors and all 50 expected inventories unknown. Taxonomy, metadata, extraction, pairing and classification attestations must come from the actual authenticated reviewers.
- Exact P5 prescribed fallback bytes, dated IBS selection/applicability and genuine missing mock/model artifacts remain source acquisition tasks. Official retrieval outcomes, affected records and next actions are recorded in the continuation report.
- A source-backed instruction-fragment successor is prepared locally. It is unapproved and unpromoted. The audited grading-role correction workflow can create its candidate; source review and administrator promotion remain required. Other malformed roots require separate evidence-backed successors; frozen history is preserved.
- Independent student-adjudicated evaluation is required before claiming calibration. The invited-student pilot has not been conducted; actual observations and resulting fixes are required before Phase 8.

No approvals were manufactured, live corpus records changed or production services deployed during this work.
