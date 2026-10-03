# Phase 3 implementation and release evidence

The textbook release is an unapproved draft. Phase 3 is not complete and the legacy taxonomy remains the serving version. Source inventories, extracted coverage, reviewed classifier readiness and May 2027 applicability are separate measures.

## Implemented behavior

- Migration `0004_textbook_taxonomy` snapshots legacy membership and adds immutable version membership, textbook artifacts/spans, descriptor revisions/approvals, reviewed crosswalks and recorded progress migrations. Original records remain intact. A successor release may reuse unchanged textbook IDs; legacy IDs and conflicting ancestry/name/sequence reuse are rejected. Artifact snapshots and source references are scoped to their version, and successor reviews start pending.
- New classification runs require the rebuilt taxonomy and reviewed terminal subtopics. Suggestions record descriptor revision, source identity, method/model and recursive ancestry. Complete-question identity survives part tags; IBS permits explicit cross-paper references. Unsupported questions enter taxonomy review.
- Model and mock papers have distinct practice document types. Course level, source attempt, target attempt and textbook applicability remain separate. Lower-level and unresolved/synthetic records cannot count as authentic Final coverage.
- Planning, coverage, scoring and API traversal are recursive and version-aware. Scores match both target attempt and taxonomy version. Unverified official priors contribute zero without changing configured weights; historical score runs remain preserved.
- Student and curator textbook explorers show source/page links, fallback/applicability, heading origin, descriptor review and predecessor history. Administrator views show sources, question families, crosswalks and the concrete release report. Authentication and personal-data ownership continue to apply.
- Release approval binds the immutable manifest and current review state. Activation is transactional, idempotent and dry-run by default. No approvals or activation are performed by the draft preparation commands.

## Source coverage and unresolved gates

The [live source audit](Phase3_Live_Source_Audit.md) records official links, selection evidence and retrieval findings. The draft contains 167 verified textbook artifacts, 6,382 nodes and 3,037 subtopics, including explicit IBS SPOM source-reference branches. P1/P2/P3 use officially ongoing May 2026 onward material; P4 combines released May 2027 chapters 1–10 with January 2026 chapters 11–28. P5 contains released module 1 chapters 1–6; its required January 2026 fallback remains unverified. Expected modules are retained in the inventory rather than disappearing from coverage.

The question inventory distinguishes all three course levels and five source families. Verified model/RTP/digest practice collections do not establish completed question extraction or reviewed classifications. Current-scheme Final mock questions remain inaccessible in the audited public sources; a schedule is not a question paper. The historical corpus inventory preserves synthetic/unresolved records and does not present them as new genuine coverage.

Source hashing and PDF page counts are independently rechecked by `scripts/phase3_prepare.py plan`. [Source review evidence](Phase3_Source_Review.md) records the heading repairs and rendered-page inspection. Complete contents/outline/body reconciliation, provision-level tax applicability, authenticated source and descriptor review, reviewed crosswalk equivalence, applicable weightage mappings and administrator approval remain release gates. Machine descriptor generation is drafting evidence only.

## Verification

The final complete isolated Python suite passes: **215 tests**. It covers selection/fallback, partial releases, identity/cycles, source routing/types, descriptor eligibility and edits, question parts/IBS references, conservative migration, score/evaluation isolation, private-data ownership, administrator gates, legacy audit separation and resumable shadow runs. PostgreSQL test containers use the existing Colima Docker context and do not touch the application volume.

The complete Chromium and WebKit suite passes: **94 tests**, followed by **12 passing explorer tests** after the artifact-schema correction. It verifies recursive navigation, fallback/legacy links, descriptor revision approval/edit behavior, concrete administrator review, permissions, and the existing private-data flows. OpenAPI and TypeScript contracts and both production distributions are regenerated; type checks pass.

The frozen composite manifest hash is `3bf74aaa4f44d5cd8518e677ca1741bda75b07dd58614c574f4d3689b71b9e4d`. All 3,037 source-section descriptor drafts remain pending; 25 retain explicit source/QA issues. Provider usage and rejected-output limitations are documented in the live source audit. No machine output counts as authenticated review.

The pre-migration checkpoint is `data/backups/caf_20261003_183208_625973_19b9aebb/manifest.json`. Restoring it in an owned temporary Colima container verified all **46 table content digests**, schema against frozen migration `0003_identity`, and **713 archived files** (336 blobs and 377 configuration files). Existing backups and the application volume remain preserved.

The measured explorer source projection is **6,175,669 bytes**, compared with **42,333,716 bytes** when complete artifact inventories were repeated per source span. Applicability basis and edition evidence remain in the explorer; full heading inventories remain in the administrator endpoint. [Payload evidence](Phase3_Source_Payload.json) records the exact manifest and span count.

The [restored migration report](Phase3_Restored_Migration.json) verifies the exact checkpoint and manifest, migration to `0004_textbook_taxonomy`, and preservation of every original value across 45 tables (excluding the intentional migration-revision change). The initial rehearsal exposed structured crosswalk evidence being sent to a text column; the corrected importer preserves it as canonical JSON text, with a regression fixture matching the real inventory. The repeated rehearsal passed.

The [application migration report](Phase3_Normal_Migration.json) records the same preservation assertions on the actual database. The [idempotent import report](Phase3_Idempotent_Import.json) verifies all 53 installed data tables survive repeated import without duplicate releases, nodes or descriptors. Apply rechecks recovery dump and archive hashes. No approval, activation, progress transfer or historical-label conversion was performed.

The [runtime inspection](Phase3_Runtime_Inspection.json) reads the actual handlers through `caf_app` and `caf_operations`. It validates all 6,382 tree members against the immutable manifest, zero eligible subtopics, disjoint rebuilt/legacy identities, and the original 380-node serving hierarchy. The complete tree response is 11,496,297 bytes; a single local load and response validation took 1.394 seconds. This is an observation, not a general performance benchmark.

The corrected read-only provenance audit at `data/audits/20261003T185932.785975Z-7a322ce5/baseline.json` reports the unchanged historical corpus categories separately from the rebuilt release: 191 confirmed synthetic, 34 suspected synthetic, 10 authentic-source-identified and 34 unresolved documents. Authentic source identification does not approve extraction or classification. Legacy descriptor coverage remains scoped to legacy IDs; the rebuilt release records 3,037 descriptor revisions and zero approvals. Audit commands create no database records.

The administrator release report explicitly names P5's missing fallback, IBS applicability/guideline/supplement-binding gaps, pending source/heading/descriptor review and representative Final-source verification. It reports `activation_ready=false`. Current-scheme mock/model/RTP classification against genuinely reviewed content remains an unmet completion gate; deterministic fixture tests prove the classification mechanism, not live corpus readiness.

Useful commands:

```sh
uv run scripts/phase3_prepare.py plan
uv run scripts/phase3_inspect.py payload
uv run caf backup run
uv run caf backup verify --dump-file <checkpoint-dump>
uv run scripts/phase3_prepare.py drill <checkpoint-manifest>
uv run scripts/phase3_prepare.py apply
uv run scripts/phase3_prepare.py apply --commit
uv run scripts/phase3_inspect.py runtime
uv run pytest -q
cd web
pnpm type-check
pnpm test:browser
pnpm build
```

`apply --commit` requires a successful restored migration for the exact manifest hash and only imports an unapproved draft. The administrator must resolve the reported gates and approve the concrete release before activation. Bulk question extraction and collaborative publication retain their Phase 4–5 responsibilities.
