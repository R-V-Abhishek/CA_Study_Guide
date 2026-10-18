# Latest application checkpoint — 18 October 2026

This checkpoint saves the latest application before production Compose or CI work.
It is not a production release or evidence of a live Ubuntu deployment.

## Included application work

- Frozen `baseline-2026-10-16` adoption and shared candidate catalogues, preserving
  personal records, original account IDs, review history and unresolved labels.
- Revisioned taxonomy index preparation and classification review exports, with
  optional free-provider classification and paid-call safeguards.
- Publication-bound original-page reading, optional extracted text, lazy source
  images, account-scoped caching and explicit complete/partial/missing answers.
- Per-account Hindi content opt-in, defaulting off, and additive migrations
  `0008_baseline_adoption` and `0009_question_language`.
- Redesigned student/review workspaces, local licensed fonts, persistent appearance
  preferences, responsive layouts and account-change protections.
- Synchronized OpenAPI/TypeScript contracts and rebuilt tracked frontend assets.
- Local launcher and application URLs standardized on `127.0.0.1:8788`.

## Corrections found during checkpoint review

The required-table backup guard did not recognize schema revision 0009. Reader,
intelligence and baseline tables are now required at that revision. A regression
test checks that successive migrations retain their predecessors' required tables.
This was a weakened validation gate, not evidence of lost backup data.

At 200% zoom the sticky reader toolbar could intercept the answer button. Scroll
margins now keep reader buttons clear of both the header and toolbar; the existing
zoom interaction test passes in Chromium and WebKit without forced clicks.

Older test expectations were updated for May 2027 defaults, current branding,
the current Alembic head, student-readable candidate catalogues, collapsed account
menus and the original-page reader default. The synthetic browser server also
resets the Hindi preference, preventing state leakage between test runs.

## Verification

- Full isolated Python suite: **474 passed**, 13 dependency/deprecation warnings.
- Workspace and browser TypeScript: passed.
- Both production frontend builds: passed.
- UI/theme unit tests: **25 passed**.
- Focused Chromium/WebKit zoom and diagnostics regression checks: **6 passed**.
- Complete Chromium/WebKit run: **233 passed of 236**. The remaining three cases
  were two Hindi preference checks affected by the old server's retained setting
  and one ambiguous search-result selector during refresh. After correcting the
  fixture reset and making the filter assertions exact, the affected tests passed
  twice per engine: **8 passed**. All 236 unique cases are therefore covered;
  this is a full run plus focused reruns, not a claim of one clean 236-test run.
- Representative desktop/mobile screenshots were inspected. Retained examples:
  [Today, desktop dark](stitch-review/chromium-today-1440-dark-viewport.png),
  [reader, mobile light](stitch-review/chromium-reader-390-light-viewport.png), and
  [review workspace, WebKit desktop](stitch-review/webkit-review-classifications-1440-dark-viewport.png).
  Remaining generated captures stay local; not every route/state received manual
  visual signoff.
- OpenAPI and generated TypeScript client regenerated from the implementation.
- Credential-pattern scan of staged text files: no matches; no live data,
  environment secrets or design-export archive staged.
- Scoped Git whitespace checks: passed. Upstream font licence bytes are preserved
  verbatim, including their existing line endings and whitespace.

Python tests use disposable PostgreSQL 16 databases, temporary storage, isolated
accounts, and blocked external/model connections. Browser tests use synthetic data
and a local OIDC provider, not production Auth0 credentials or restored personal data.

### Local environment limitation

Colima failed to forward newly published loopback database ports automatically.
Tests used fixed ports and temporary loopback-only SSH forwards into the VM.
These were operational test aids, not application or production firewall changes.
Existing database/browser containers were preserved.

## Release boundary

Live documents, database contents, local recovery snapshots, secrets and the design
export remain outside Git. The baseline manifest identifies content; Git alone
does not recreate the adopted corpus. Production installation still needs a
verified recovery snapshot and separately supplied configuration.

No production Compose, GitHub Actions, Ubuntu application installation, real Auth0
login verification or production import is included in this checkpoint.
