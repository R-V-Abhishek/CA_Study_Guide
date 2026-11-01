# Archived verification reports

These reports record what was built and checked at each implementation phase. They are evidence of the
state at their date, **not** current status: several describe production as not yet installed. For the
current state read [Home_hosting.md](../Home_hosting.md) and [Architecture.md](../Architecture.md).

Machine-readable evidence (`docs/Phase*_*.json`, baseline manifests, receipts) stays in `docs/` because
scripts and `caf_l5.coverage` read and write those paths. Screenshots written by the browser suite stay in
`docs/phase7-screenshots/` and `docs/stitch-review/`.

| Phase | Report | Topic |
|---|---|---|
| 0 | [Phase0_Verification.md](Phase0_Verification.md) | Recovery and verification gate |
| 1 | [Phase1_Verification.md](Phase1_Verification.md) | Backend fixes and migration baseline |
| 2 | [Phase2_Verification.md](Phase2_Verification.md) | Auth0 sign-in, private ownership, restricted database roles |
| 3 | [Phase3_Verification.md](Phase3_Verification.md), [source review](Phase3_Source_Review.md), [live source audit](Phase3_Live_Source_Audit.md) | Textbook taxonomy and sources |
| 4 | [Phase4_Verification.md](Phase4_Verification.md), [continuation queue](Phase4_Continuation_Queue.md) | Acquisition and extraction |
| 5 | [Phase5_Verification.md](Phase5_Verification.md) | Classification revisions and publication |
| 6 | [Phase6_Verification.md](Phase6_Verification.md) | Published question reader and scoring |
| 7 | [Phase7_Verification.md](Phase7_Verification.md), [corpus continuation](Phase7_Corpus_Continuation.md), [usability pilot](Phase7_Usability_Pilot.md) | Workspace UI and corpus readiness |
| 8 | [Phase8_Verification.md](Phase8_Verification.md), [local acceptance](Phase8_Local_Acceptance.md), [cost control](Phase8_Cost_Control.md), [real data preview](Phase8_Real_Data_Preview.md) | Home deployment preparation |
| UI | [Stitch_UI_Verification.md](Stitch_UI_Verification.md) | October 2026 interface redesign |
