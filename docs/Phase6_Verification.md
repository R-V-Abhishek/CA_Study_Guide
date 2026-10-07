# Phase 6 verification

Phase 6 implements complete published-question reading, publication-bound search and source access, explicit personal attempt/taxonomy contexts, reviewed corpus completeness, persisted score explanations, durable recomputation and syllabus-based planning. The mechanisms are demonstrated with isolated reviewed fixtures. **Live corpus approvals remain deferred.** Phase 5's 120 Luna suggestions remain experimental; no student reviews or corpus-wide readiness are manufactured.

## Reader and publication

Migration `0007_question_reader` adds immutable `core.published_question` and `core.published_source` snapshots, explicit occurrence identities, current publication pointers and appearance/question/part bindings. Phase 5 publication and administrator replacement create the reader snapshot in the same transaction. Verification counts and disputes remain separate live review records. Backfill projects only already-reviewed, nonexperimental publications and adds no reviews.

`GET /api/v1/questions/{question_id}` returns the complete stem, case, ordered parts, available answers, answer/MCQ/choice structure, marks, reviewed mappings, taxonomy paths, source hashes/pages/assets and revision references. `/questions` provides pagination and paper/subtopic/attempt/source/answer filters; `/search` uses PostgreSQL full-text indexes over published context, taxonomy paths and metadata. Private notes are restricted to the authenticated owner. `/appearances/{appearance_id}` resolves reliable bindings and reports legacy provenance limitations explicitly.

The student `/questions/:questionId` route keeps sibling parts and shared context visible, highlights an optional part, reveals answers deliberately, reports partial/missing answers and distinguishes whole/offered/selectable/attributed marks. Source PDF and page/asset endpoints authenticate the request, require a current publication reference and verify recorded hashes under the content-addressed blob store. Arbitrary file paths are rejected. Reading does not mutate syllabus progress. Return links are restricted to internal student routes; filters are retained.

Confirmed paper/answer pairs with matching paper, attempt, series and question labels share canonical occurrence identity. Confirming or revoking pairing evidence reconciles previously published occurrences without rewriting immutable question content. Practice reuse retains a separate occurrence. Standalone answer identity and conflicting pair evidence remain ambiguous. Marks allocation uses disjoint gradable leaves and normalized primary/secondary shares. Parent totals are retained separately; unknown marks and unresolved OR allocations do not enter aggregate signals.

## Context, completeness and scores

Personal serving resolves profile → target attempt → reviewed taxonomy binding → pinned scoring configuration → successful snapshot. Binding absence produces explicit readiness; it never selects a globally active rebuilt taxonomy or another attempt's run. Approved historical bindings remain usable. Applicability exclusions and unresolved fallback applicability constrain syllabus scope, progress, plans and revision queues. Student credentials read published `core` projections without staging access.

`intel.corpus_coverage` stores reviewed expected inventory, discovery/acquisition, metadata/extraction/pairing status, official question scope, gradable accounting, label/occurrence completeness, publication counts, missing answers and blockers. `GET /api/v1/coverage` exposes these states. Inventory seeding preserves unknown expected scope and imports continuation reasons without granting approvals. Missing answers alone do not invalidate a complete question paper. Neither one publication nor a marks-total match proves completeness.

Exam components and frequency use complete reviewed paper-attempts before the selected target. Published occurrence/marks contradictions also remove an attempt from the usable denominator. Practice requires confirmed dated reviewed occurrences; undated collections remain readable and searchable. Same-target dated practice can contribute with age zero; exam frequency remains strictly historical.

New score runs persist exact publication/occurrence/coverage/prior/configuration inputs and generation. Each topic retains raw decayed marks, paper-wide normalization denominators, normalized components, configured weights, weighted contributions, included occurrences and exact frequency attempts. Full importance is unavailable when any component is unavailable; a known weighted subtotal is returned separately. Legitimately observed zero denominators yield normalized zero. Weights remain 60% exam, 20% practice, 20% prior unless the bound configuration says otherwise. Only reviewed version-bound priors with verified official weightage-source evidence enter the prior component; generated legacy priors are excluded from rebuilt-taxonomy scores.

Explanations use immutable persisted contributions and snapshot configuration. The importance formula is reproducible from the displayed normalized contributions; raw marks are not presented as percentages. Historical importance is a relative study signal. Frequency describes its exact usable reviewed subset, with unavailable frequency when there is no denominator.

## Jobs and personal guidance

Current score snapshots are scoped by attempt, taxonomy and configuration. PostgreSQL jobs coalesce pending contexts, claim work with `SKIP LOCKED`, retain retryable leases and failures, and compute under a consistent transaction snapshot. Completion must own an unexpired lease; older or stale outputs cannot replace newer successful scores. Corpus mutation advances a monotonic generation and transactionally invalidates eligible known contexts. Newly reviewed contexts receive initial jobs through worker discovery. Publication is readable immediately; context freshness reports publication/scored generations, computation time and pending/running/failed status.

Scored plans require usable full importance for all selected syllabus items. Otherwise reviewed syllabus order and actual personal progress supply a clearly labelled syllabus plan. In-progress items precede not-started items; budget, block duration, selected papers/groups and chapter caps apply. Responses include allocated/unused minutes and snapshot/context identity. Personal progress uses honest unweighted counts when reviewed priors are unavailable. Revision queues are profile-specific and ordered by due date without scores. Settings/progress mutations invalidate query caches; account-owned note drafts survive same-account context changes.

The existing startup starts and monitors the intelligence worker. Shutdown identifies its recorded PID by an ownership token before signalling it. Pending work survives in PostgreSQL.

```sh
uv run caf intel enqueue --target-attempt 2027-05 --taxonomy-version VERSION
uv run caf intel worker --once
uv run caf intel status --target-attempt 2027-05 --taxonomy-version VERSION
uv run caf intel backfill-reader
uv run caf intel seed-coverage --taxonomy-version VERSION
```

Administrator `POST /api/v1/curate/intel/recompute` returns HTTP 202 with a coalesced job identity; it does not compute synchronously.

## Verification and retained gates

Verification completed on 2026-10-07:

- `uv run pytest -q`: **344 passed**. The missing-profile-settings regression is covered; focused Phase 6 context/reader/intelligence/recovery tests also passed.
- `pnpm --dir web type-check`: passed. `pnpm --dir web build`: student and curator production assets built. The student JavaScript chunk is 512.68 kB and triggers Vite's existing 500 kB advisory; gzip size is 156.60 kB.
- `uv run scripts/phase6_verify_contracts.py`: OpenAPI, generated TypeScript and both production asset manifests verified together; the build identity and asset hashes are recorded in [build verification](Phase6_Build_Verification.json).
- `pnpm --dir web test:browser`: **126 passed** across Chromium and WebKit. The 16 authentication cases were rerun after the incomplete-profile fix: **16 passed**, with no server exception.
- Migration `0006_classification_revisions → 0007_question_reader` preserved all original values across 65 tables. The frozen migration hash is `63030852f028c866adae5c760770fc1bdb67fe47ef9702ff0325d924ee04d1a1`.
- Backup/restore verified revision `0007_question_reader`, all 74 tables and all 5,351 archived files, including the 1,010 frozen Phase 5 artifacts. See [normal migration report](Phase6_Normal_Migration.json), [restored migration report](Phase6_Restored_Migration.json) and [recovery report](Phase6_Recovery_Verification.json).

Live data remains intentionally unapproved: 120 Luna suggestions are experimental; there are zero reviewed classification revisions and zero published snapshots. The 50 seeded coverage rows retain unknown expected inventory and unreviewed status. No attempt-taxonomy bindings were created. The migration and restore checks did not fabricate reviews or promote the draft taxonomy.

The [Phase 4 continuation queue](Phase4_Continuation_Queue.md) and [Phase 5 deferred corpus gates](Phase5_Verification.md#deferred-corpus-gates) remain outstanding for final UI/readiness work: taxonomy/source/descriptor approval, official attempt bindings, metadata conflicts, extraction layouts and genuine whole-question accounting, paired-answer review, unresolved optional-mark allocation, expected inventories and official weightage mappings. Phase 7 owns the broader visual redesign. Experimental classification outputs do not clear any of these gates.
