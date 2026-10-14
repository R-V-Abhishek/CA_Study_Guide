# Phase 8 local experience review

Status: baseline preview prepared; human judgments pending. This is not production acceptance.

**14 October update:** the user's review now uses the [real-data preview](Phase8_Real_Data_Preview.md) at http://127.0.0.1:8788/__preview. The synthetic harness below remains available for automated scenarios; it is not the requested human preview.

Open **http://127.0.0.1:8787/__acceptance** on this Mac. The start page provides synthetic Student A, Student B and Administrator buttons, direct reader examples, and a feedback form for each acceptance area. These identities are distinct from real administrator account 1 and the nominated pilot student.

Review navigation, appearance, the complete long case/table, complete/partial/missing answers, topic importance, private notes, progress, plans, revision and access controls. Use **Approved / Changes requested / Not tested**, the affected screen and your observation. Resize the window to inspect mobile layouts; this loopback-only preview is not directly accessible from a phone.

The acceptance banner is visible in both applications. Sources, scores and publication snapshots are synthetic. No real credentials are needed, no live content is approved and no personal records are migrated. Cookies have dedicated acceptance names so another local installation's session is not replaced merely because it uses the same hostname on a different port.

The May 2026 profile shows populated synthetic study workflows. Selecting May 2027 in Profile shows the unavailable binding/score context; return to May 2026 afterward. Switch identities from the acceptance start page. Use separate browser profiles or private windows for simultaneous identities; two tabs in one profile share cookies.

The current classification screen exposes honest source/extraction/taxonomy blockers. Eligible publishing/verification, stale concurrent review, source-backed extraction correction and successor taxonomy scenarios are explicitly marked pending. Do not approve those from static or blocked examples. They require later isolated fixtures and Phase 8 implementation before their human review.

## Operator lifecycle

Use the existing pinned tools; do not connect the harness to the corpus database:

```sh
uv run scripts/browser_server.py --acceptance
```

The command owns a temporary PostgreSQL container and temporary source/feedback directory. It binds the passwordless acceptance harness to `127.0.0.1`; the ordinary browser runner keeps its previous configuration. `CAF_BROWSER_PORT` overrides the default 8787 when needed.

The reviewed local instance uses `--database-port 5439`, after checking that this host/VM port was unused and establishing its Colima forwarding. Without this optional flag, the sandbox keeps its existing random-port behavior. A requested occupied port fails; no existing service is stopped or replaced.

Feedback is available from `/__acceptance/feedback` and persisted to `human-acceptance.json` in the owned temporary directory. Export genuine observations to the Phase 8 evidence before stopping or resetting the process. Server shutdown removes the disposable environment; this preview does not promise restart persistence. The existing operator-only test reset also clears acceptance observations. Automated test feedback is labelled and must not be counted as human approval. Do not run destructive harness resets during a human review.

```sh
CAF_BROWSER_PORT=8787 CAF_BROWSER_EXTERNAL=1 pnpm --dir web exec playwright test phase8-acceptance.spec.ts
```

Run existing regression tests against their original fixture environment, not the acceptance dataset: the original search test intentionally assumes no missing-answer sample. The new acceptance tests skip when the acceptance endpoints are absent.

On this installation, Colima's automatic forwarding failed for newly published PostgreSQL ports even though PostgreSQL was ready inside the VM. The implementing agent established forwarding for the exact owned sandbox ports through the existing SSH connection, without restarting Colima or existing services. Host endpoint readiness is now verified before migrations start. A future failed forward requires inspection of the current Colima connection and owned port, not reuse of stale process/port identifiers.
