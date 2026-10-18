# Phase 8 verification

Date: 10 October 2026. Branch: `feat/phase8-central-deployment`.
Status: **October 16 baseline adoption replaces the local acceptance gate; central deployment remains pending**.

## 16 October: baseline study and review

`baseline-2026-10-16` is the accepted starting corpus for study and review targeting May 2027. Import and activation must validate its frozen 3,009 roots, 7,778 gradable parts, 3,300 catalog nodes and source hashes; adoption records administrative authority without fabricating student verifications. Incomplete answers, extraction concerns and uncertain applicability remain visible.

The standard persistent application uses http://127.0.0.1:8788 with normal Auth0 authentication. The disposable real-data launcher, synthetic acceptance landing page, checklist, account buttons and banners are retired. Ordinary automated browser fixtures retain complete/partial/missing answers and full source pages, with study/review regressions in `baseline-study.spec.ts`. Application operation is documented in [local study and review](Phase8_Local_Acceptance.md).

No local experience sign-off is required before further engineering. Cloud deployment, spending controls, encrypted backups/recovery, production authentication, capacity and operational verification remain required. Baseline adoption does not complete Phase 8 central deployment.

### Current local verification

- The baseline/publication/reader/taxonomy/migration suite passed: 66 tests, including 18 adoption and 13 frozen-pack tests. Related API/batch/context/intelligence/readiness checks passed (62 initially); the two environment-blocked worker/recovery checks passed after disabling dependency sync and forwarding the owned restore port.
- The actual pre-adoption backup independently restored with all 74 table digests, source/config files and schema matching. The retired preview was backed up separately before shutdown. Input archive verification covered all 6,805 pinned files.
- Exact corpus identities, per-paper coverage, hash authorization, interrupted preparation, transactional activation, retry conflicts, missing answers, unresolved labels, actual database capabilities and preservation of later corrections/personal records have targeted regressions. Operational details are in [the baseline record](Baseline_2026_10_16.md).
- Persistent activation completed under taxonomy version 9. [Actual data verification](Baseline_2026_10_16_Verification.json) confirms 3,009 published roots, 7,778 parts, all 691 corrected routings, 3,300 labels, 94 question PDFs, the previous 120 suggestions and zero student attestations. Answers remain 409 complete, 189 partial and 2,411 missing.
- Direct handler measurements with actual database roles: search returned 25 of 687 matching roots in 0.0334 seconds; a 100-root review page took 2.4135 seconds with a 2,286,088-byte JSON response and shared catalog references. These timings exclude HTTP transport and browser rendering. Database size grew from 543,079,447 to 636,574,743 bytes; the 857,913,882-byte source store and its 3,911 files were unchanged. The separately preserved input archive is 1,314,242,560 bytes.
- The real rollback operation restored the previous publication state inside a transaction; discarding the drill retained the active baseline. [All 12 personal/identity tables](Baseline_2026_10_16_Personal_Preservation.json) match the pre-adoption backup after normalizing account 1's target change. [Restart verification](Baseline_2026_10_16_Restart.json) confirms persistent publications and May 2027 settings; recompute job 1 completed successfully. Its 2,043 scored nodes have zero authoritative importance values, preserving the unresolved coverage/applicability limits.
- Final launcher/worker health and publication checks passed after a controlled restart. Database size after recomputation and final verification was 645,512,215 bytes, a total increase of 102,432,768 bytes from the initial measurement. The preceding storage/timing figures describe the earlier post-activation, pre-recompute measurement.
- Workspace and browser TypeScript checks passed.
- Both production frontend builds passed; the standard application assets were rebuilt.
- Python launcher/harness compilation and whitespace/diff checks passed.
- Loaded persistent settings match May 2027, `http://127.0.0.1:8788`, its callback and allowed origin, without changing provider credentials.
- Replacement browser tests were attempted. A fresh owned PostgreSQL sandbox failed host readiness on its published port (the diagnosed Colima forwarding issue); no test ran. A second attempt against the existing synthetic harness failed before assertions because Chromium's Mach port registration and WebKit startup abort in this execution environment. Browser verification remains pending; historical passes below do not cover the replacement suite.
- Native-browser inspection of the persistent standard origin showed the ordinary sign-in screen, without preview controls or banners. Clicking “Sign in with Auth0” returned HTTP 500 at the local login route before provider redirection. The server traceback identifies `httpx.ConnectError: [Errno 8]` while resolving Auth0 discovery metadata, matching the host DNS failure also seen for PyPI; this is not evidence of an Auth0 callback allowlist mismatch; provider allowlists and an authenticated study/review screenshot remain unverified. No passwordless bypass or identity changes were used.

## Historical evidence from 10–14 October

The following results describe the earlier disposable environments, which have since been retired. They remain evidence of those checks; their old operating commands and acceptance prerequisite no longer apply.

## 14 October: actual corpus preview

At the user's request, prepared a [real-data preview](Phase8_Real_Data_Preview.md) using a read-only snapshot of the existing corpus instead of synthetic fixtures. All 74 restored table digests matched before copy-only credentials and paths were changed. The copy contains 521 source documents, 120 classification suggestions and no published study questions. The original source/content approval state is preserved.

Real-data inspection exposed repeated loading of the same taxonomy evidence per question in the review queue. The queue now shares evidence only within a read request; mutations and later requests reload it. Focused API/publication checks passed (22 tests, 11.90 seconds). A real 100-record queue request took 3.533 seconds locally; an original 25-record request exceeded 60 seconds. Central deployment and production latency acceptance remain pending.

The full 120-record queue subsequently loaded in 4.439 seconds. Original PDF bytes and rendered page access were verified, and an actual case-study question was inspected in the browser. After these checks, all 74 original table content digests remained unchanged.

## Completed in this checkpoint

- Confirmed GitHub repository administrative access and local Auth0 configuration presence without exporting credentials.
- Verified the user's existing ₹500 enforced Cloud Run cap in the signed-in Google console without saving changes. Scope and limitations are recorded in [cost controls](Phase8_Cost_Control.md).
- Retained real administrator account 1 as the intended production administrator. The nominated first pilot student is recorded in the conversation; no invitation has been sent or production student provisioned.
- Extended the existing disposable browser harness with an explicit `--acceptance` mode. Two synthetic students and an administrator use the actual cookie-backed identity and restricted database capabilities.
- Added a labelled start page and feedback forms, complete/partial/missing answer samples, a long case/table and its complete two-page source PDF. Both interfaces carry a synthetic acceptance banner.
- Acceptance controls bind only to loopback, require the test environment, and use dedicated cookies so another local application's session is not replaced. Feedback writes enforce authenticated identity, CSRF and account expectations. They never create live corpus attestations.
- Verified database readiness through the actual host endpoint before migrations. Added an optional owned database port for this installation's diagnosed Colima forwarding failure. Existing services and the original corpus database were preserved.

## Technical evidence

| Check | Result |
| --- | --- |
| Focused Python reader and identity checks | 34 passed, 9.81 seconds |
| Original-fixture reader, identity and personal-study browser regressions | 72 passed across Chromium/WebKit, 1.6 minutes |
| New acceptance identities, banner/navigation clearance, cookie separation, complete/partial/missing answers, PDF access and feedback | 6 passed across Chromium/WebKit, final run 6.4 seconds |
| Acceptance layouts at 390/768/1280/1440px, light/dark | All 8 existing responsive journey checks passed in the initial acceptance run |
| Workspace TypeScript and browser TypeScript | Passed |
| Generated long-case PDF | 2 pages; final case paragraph, table, both parts and final answer retained |
| Whitespace/diff checks | Passed |
| Human feedback before handoff | Empty; explicitly automated test observations were cleared after checking their provenance |

[Visually inspected student preview](Phase8_Acceptance_Preview.jpg). Inspection caught a preview-only banner overlapping the fixed navigation heading; the harness offsets navigation by the measured banner height, and both browsers verify clearance. The application styles remain unchanged.

The initial mixed-dataset regression run assumed no missing-answer sample and reported two expected fixture-assumption failures. An initial Safari block-duration check also failed; its rerun against the original fixture passed. The final 72-test original-fixture run passed, including that path. This is not a claim that every Phase 7 test or the complete release suite was rerun.

Frontend application code, production OpenAPI contracts and compiled frontend assets were not changed in this checkpoint. Production builds, HTTPS provider flows, runtime durability and cloud latency/capacity remain release-stage checks.

## Reproduce

```sh
uv run pytest -q tests/test_phase6_reader.py tests/test_phase2_auth.py
pnpm --dir web type-check
pnpm --dir web exec playwright test baseline-study.spec.ts questions.spec.ts
```

For existing regression tests, use a separate ordinary `scripts/browser_server.py` instance and its original fixture dataset. The final regression run omitted the already-passed responsive journeys with `--grep-invert 'student working routes'`.

## Remaining deployment work

Isolated staging access/region/capacity validation, private storage adaptation, immutable packaging, bounded cloud jobs, proposed-label feedback, administrator taxonomy preparation/migration preview, staged corpus restore, production HTTPS authentication, recovery drills, measured latency/cost and approved cutover remain to be implemented and verified. Daily encrypted backups and an independent source mirror need a destination decision before production migration. The initial one-student pilot does not yet satisfy the original 5–15-user criterion.

The historical acceptance and real-data previews do not establish production migration, invitation delivery, paid infrastructure readiness or production latency guarantees.
