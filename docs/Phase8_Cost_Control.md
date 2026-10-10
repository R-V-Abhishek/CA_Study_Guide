# Phase 8 cost controls

Status: initial account inspection; no cloud resources deployed by this work.
Date: 10 October 2026.

## User policy

- Actual monthly spending target: ₹0. Do not treat free allowances as a guaranteed zero bill.
- The user has configured a ₹500 Google Cloud budget/cap. This does not authorize automatic upgrades or optional paid capacity.
- Neon must remain on Free. No paid AI calls, custom domain, always-on worker or minimum Cloud Run instances are authorized.
- Explain projected nonzero expenses and obtain a decision before introducing them. Infrastructure measurements and the concrete release/cutover report precede production approval.

## Verified existing Google control

The signed-in Google Cloud console was inspected without saving changes. The `study-guide` budget in project `ca-study-guide1` shows:

| Setting | Observed value |
| --- | --- |
| Budget period | Monthly |
| Spend cap enforcement | Selected; status Configured |
| Spend cap amount | ₹500 |
| Scope | Cloud Run in CA-Study-Guide |
| Alert thresholds | 50%, 80%, 100% (₹250, ₹400, ₹500) |
| Displayed estimated spend | Approximately zero at inspection; not an invoice verification |
| Next reset shown | 1 November 2026 |

This is an enforced **Cloud Run** cap, rather than an alerts-only budget. Its scope does not establish limits for image registry storage, build services, scheduling, logging or other supporting services. Their actual usage, free allowances, retention and controls must be checked before deployment.

[Google's spend-cap documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) states that enforcement uses gross estimated costs before savings/credits, is delayed, and automatically resets each budget period. It is not an exact total-invoice ceiling. A deliberate pause procedure must remain paused independently of that automatic reset.

## Pending before cloud release

- Verify billing account usage shared by the free allowances, region-specific networking costs, and registry image size/retention.
- Measure database, history/index and source-object consumption against the actual Neon Free limits.
- Verify private storage capabilities and region in the nominated Neon project.
- Prepare supporting-service alerts, bounded web/jobs configuration and a tested pause procedure without increasing the existing cap.
- Present estimated actual cost alongside measured warm/cold latency and concurrent capacity. No production latency or ₹0 invoice guarantee has been established.
- Choose and test the independent backup destination before production cutover; the user deferred this decision.

Source: [Cloud Run pricing](https://cloud.google.com/run/pricing).
