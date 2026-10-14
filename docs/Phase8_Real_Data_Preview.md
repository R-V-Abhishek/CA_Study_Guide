# Real-data local preview

Prepared on 14 October 2026 at http://127.0.0.1:8788/__preview.

This preview contains a verified copy of the existing local corpus and source PDFs. No synthetic accounts, questions, publications, scores or approvals are added. The actual administrator profile (account 1) is used in the copy. The original database is read only during snapshot preparation; preview edits affect a disposable PostgreSQL container and copied files.

The current corpus contains 521 source documents, 120 classification suggestions and zero published student questions. Its student context reports `taxonomy_binding_unavailable`. Review the actual questions, extraction evidence and source PDFs in the curator app. The student app shows the actual incomplete-corpus experience; this preview does not manufacture a populated approved study library.

Use **Study / review** in the banner to switch between the student interface and actual review backlog. Both use the same copied administrator profile. This is not a demonstration of a separate invited student's identity or production Auth0 login.

## Operator lifecycle

```sh
uv run scripts/real_data_preview.py --database-port 5442
```

The existing backup implementation captures one read-only database snapshot, archives sources with file digests, and restores it into an owned container. All 74 restored tables are compared with the source snapshot's row counts/content digests before preview-specific changes. The copy receives fresh restricted role credentials; imported sessions, pending logins and invitations are invalidated in the copy. Dedicated preview cookies avoid replacing another local app's session.

The preview's passwordless account button is available only on loopback and only in this restored copy. No preview controls are installed in the serving application. The command requires local development configuration and rejects use against the synthetic test harness. No migrations or role grants run against the original database.

For this Colima installation, forward the selected unused database port through the inspected current Colima SSH connection before starting. The optional port setting never replaces an occupied service. The current background instance logs to `/private/tmp/caf-real-preview-5442-v2.log`. Its files and database remain available while the background process runs. Shutdown removes the copy; export any desired preview edits before stopping it. They are not automatically imported into the original corpus.

## Verification

- All 74 restored table digests matched the source snapshot before preview credential/path changes.
- Actual account identity, 521 source records and honest student readiness were verified through the API.
- The first 100 actual review records loaded in 3.533 seconds locally after fixing repeated taxonomy evidence loads. Before the fix a 25-record request exceeded 60 seconds. This is a local observation, not a production latency result.
- Publication/identity/revision checks: 22 tests passed in 11.90 seconds, including a regression that evidence is shared within one queue request and reloaded after a taxonomy change.
- Original PDF and rendered source-page access are checked separately from extracted question text.
- All 120 real queue records were retrieved in 4.439 seconds locally. Original document 516's PDF (277,306 bytes) and rendered PNG page were verified, and the actual case-study workspace was visually inspected.
- After preview testing, all 74 original database table content digests still matched the source snapshot.

The queue now loads taxonomy evidence once per version within each read request. Publication mutations still reload current evidence and enforce their existing gates. No evidence is cached between requests.

On hosts needing an explicitly forwarded test port, the test harness accepts `CAF_TEST_DATABASE_PORT`; its default remains a random owned port:

```sh
CAF_TEST_DATABASE_PORT=5443 uv run pytest -q tests/test_phase5_api.py tests/test_phase5_publication.py
```
