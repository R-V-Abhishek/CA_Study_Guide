# Phase 8 verification

Date: 10 October 2026. Branch: `feat/phase8-central-deployment`.
Status: **local baseline acceptance prepared; human approval and central deployment pending**.

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
uv run scripts/browser_server.py --acceptance
CAF_BROWSER_PORT=8787 CAF_BROWSER_EXTERNAL=1 pnpm --dir web exec playwright test phase8-acceptance.spec.ts
```

For existing regression tests, use a separate ordinary `scripts/browser_server.py` instance and its original fixture dataset. The final regression run omitted the already-passed responsive journeys with `--grep-invert 'student working routes'`.

## Remaining gates

The user judges the [local experience](Phase8_Local_Acceptance.md) before central provisioning. Record actual judgments and fix/retest requested changes. Eligible publication/verification, simultaneous stale review, extraction correction and successor taxonomy scenarios are explicitly marked pending rather than presented as completed acceptance.

After that gate: isolated staging access/region/capacity validation, private storage adaptation, immutable packaging, bounded cloud jobs, proposed-label feedback, administrator taxonomy preparation/migration preview, staged corpus restore, production HTTPS authentication, recovery drills, measured latency/cost and approved cutover remain to be implemented and verified. Daily encrypted backups and an independent source mirror need a destination decision before production migration. The initial one-student pilot does not yet satisfy the original 5–15-user acceptance criterion.

No application release, source/content approval, production migration, invitation send, paid infrastructure expansion or production latency guarantee is claimed by this report. Deployment and taxonomy-update runbooks will accompany the implemented central workflows; this checkpoint's operator instructions concern the local acceptance harness only.
