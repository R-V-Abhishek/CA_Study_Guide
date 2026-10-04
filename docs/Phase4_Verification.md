# Phase 4 verification

Observed 4 October 2026. Acquisition, candidate extraction, curator interfaces and recovery mechanisms are implemented and tested. **The Phase 4 completion gate remains open:** the live corpus is unapproved, metadata conflicts and source pairs require review, generic layouts have extraction concerns, and authentic fixtures do not yet cover every paper/profile combination. No new questions were published or classified against an unreviewed textbook release.

## Acquired sources and extraction outcomes

The frozen Phase 3 inventory remains unchanged. Its successor [inventory](Phase4_Acquisition_Inventory.json) contains 494 records, including separately inventoried older material and excluded Foundation/Intermediate sources. [Source coverage](Phase4_Source_Coverage.json) records every association, original/final URL, artifact outcome, source identity, response evidence and SHA-256. Discovery follows official journal and weekly-practice navigation as well as paper/attempt navigation.

| Family | Acquired associations | Distinct PDF hashes | Remaining limitation |
|---|---:|---:|---|
| RTP | 67 | 67 | Confirm metadata and review paper-specific layouts |
| Examination questions and suggested answers | 100 | 100 | Includes unresolved paper/attempt identities; confirm actual companion pairs |
| Model collections | 2 | 2 | Combined-paper ranges require administrator confirmation; source attempts remain nullable |
| IBS digests, journal and weekly practice collections | 111 | 93 | Review collection/case identities, companion answers and facts-only cases |
| Current Final mock papers | 0 | 0 | Browser navigation returned announcements without question/answer artifacts |
| **Total** | **280** | **262** | Byte acquisition is distinct from metadata approval |

The 18 duplicate-byte associations retain their source links. The 100 examination associations comprise 36 question papers and 64 suggested-answer sources. There are 15 older-scheme records, 197 lower-level records and two announcement records outside the acquired Final artifact total. The isolated [mock browser audit](Phase4_Mock_Browser_Audit.json) records explicit missing-artifact/zero-document outcomes; schedules and login/download failures cannot count as papers.

| Navigation attempt or collection | Acquired associations |
|---|---:|
| May 2024 | 16 |
| November 2024 | 24 |
| May 2025 | 19 |
| September 2025 | 26 |
| January 2026 | 21 |
| May 2026 | 22 |
| November 2026 RTP navigation | 9 |
| Undated collections or unresolved attempts | 143 |

These are discovered navigation identities, subject to content confirmation. In particular, scanned examination headings contradict some group-level paper assignments. A cover's applicability statement cannot supply the source attempt of an undated model/IBS collection. Source attempt, collection identity, textbook edition, target attempt and taxonomy version remain separate.

The final candidate run records all 280 acquired associations in [extraction coverage](Phase4_Extraction_Coverage.json): 199 candidate associations, 80 metadata-review outcomes and one provenance-review outcome. The 199 associations reference **181 distinct candidate revisions**, all unapproved. Combined PDFs without confirmed ranges and contradictory metadata remain queued rather than being assigned wholesale to one paper.

| Current inferred paper | Distinct candidate documents | Assembled roots | Analytical parts |
|---|---:|---:|---:|
| P1 | 44 | 822 | 2,341 |
| P2 | 9 | 79 | 534 |
| P3 | 7 | 380 | 758 |
| P4 | 15 | 617 | 1,187 |
| P5 | 8 | 252 | 602 |
| P6 | 98 | 759 | 1,840 |
| **Total** | **181** | **2,909** | **7,262** |

Root/part totals are parser output counts, **not certified complete questions**. Runtime validation checks all 2,909 contracts and their source bounds. Machine answer statuses are 396 complete, 186 partial and 2,327 missing; some missing answers belong to question-only/facts-only sources. Every candidate still needs human review. The [runtime inspection](Phase4_Runtime_Inspection.json) provides the full paper × attempt/collection × family × profile × outcome matrix, separate quality dimensions, actual review counts and authentic-fixture gaps.

## Implemented behavior

- HTTP/browser/manual acquisition shares PDF validation, immutable acquisition receipts and content-addressed storage. Existing URLs with changed bytes produce successor artifacts; identical bytes preserve their associations. Browser discovery uses isolated contexts and reports failed/empty/partial results explicitly.
- Profiles declare question/answer roles, layout, numbering scope, answer expectations and marks rules. Segmentation maintains independent answer state, nested parts, shared cases, repeated labels, MCQ options/keys, OR alternatives and continuations. Answer-only sources retain evidence without producing question duplicates. Unsupported profiles and OCR failures remain actionable states.
- Native extraction persists ordered raw and normalized blocks, page/bounding-box evidence and origin. Selective OCR uses configured Tesseract, caches by source/page/configuration, and reports unavailable workers. Source pages/crops preserve uncertain tables, formulas and diagrams for review; numerical answers are never rewritten by an LLM.
- Confirmed document pairs precede scoped part matching. Actual answer PDF spans and competing literal candidates survive assembly. Administrators can select a recorded candidate through an audited immutable correction; text replacement cannot silently resolve an ambiguous answer. Literal MCQ keys do not acquire invented explanations.
- Runtime whole-question responses assemble shared stems once, ordered question/answer trees, correspondence, choices/marks/options/keys, assets and source evidence. Quality tracks metadata, questions, answers, pairing, ordering, marks/choices, readability and human review independently.
- Re-extraction writes candidates first, reconciles full content/provenance digests and scoped identity, and requires an explicit revision check for promotion. Exact split/merge evidence is review material; changed/unmatched published content remains retained and flagged. Failures and concurrent/stale promotions preserve the previous current revision. Identical runs do not duplicate current units or attestations.
- The curator route `/curator/extraction` supports original-page access before extraction exists, metadata/range confirmation, complete trees, quality reviews, source pairing, revision comparison, audited corrections and promotion. Active students can review extraction quality; administrators confirm metadata/pairs and promote. Source pages/assets use authenticated ID-based endpoints and validated bounds. Unpublished extraction stays in this workspace.
- Classification consumes the root context, relevant part and available answers, and checks both actual extraction reviews and version/subtopic eligibility. Revoked pairs or changed metadata invalidate readiness. The `textbook-v1` draft has zero eligible subtopics for each paper; no automatic review evidence was fabricated.

## Verification and recovery

Targeted acquisition, segmentation, revision, pairing, concurrency, protected-source, permission and classification tests precede the full suites. The final full Python suite passes **274 tests**, with 11 upstream deprecation warnings; the shared-stem change also passes **46 focused extraction tests**, and the disk-storage fix passes **24 recovery/isolation tests**. Chromium/WebKit pass **112 browser checks**, including all 18 extraction workspace checks. TypeScript checks and both production builds pass. [Build verification](Phase4_Build_Verification.json) confirms that runtime OpenAPI matches the checked-in schema and records the regenerated TypeScript contract and both production asset hashes.

Eight authentic source-backed fixtures cover P1 RTP case/structured question, IBS digest case, separate and mixed P1 model layouts, a scanned P3 case with OCR, and a facts-only IBS practice case. Literal expected trees/blocks and original page renders were inspected by the agent and exercised by regression tests. **These checks are not authenticated human approvals.** The runtime fixture matrix records 38 remaining paper/profile gaps; synthetic tests do not establish their live coverage. Generic suggested-answer and examination segmentation still produces uncertain numbering, marks and layout results and must be reviewed against original pages.

Migration `0005_extraction_revisions` is forward-only. The [restored migration drill](Phase4_Restored_Migration.json) restores the Phase 3 checkpoint exactly, applies the new migration and compares all 53 preserved original table projections; the migration-version table changes as expected. [Normal migration evidence](Phase4_Normal_Migration.json) records application to the working database. Runtime preservation checks confirm unchanged original values across 29 personal-data, decision, publication, taxonomy and unit/answer/tag tables, including the original 1,596 units, 360 answers, 195 decisions and 25 published appearances. The frozen taxonomy files are unchanged.

Worker grants include the new ingest records with separate review permissions. Backups archive source bytes, OCR caches, acquisition receipts, extraction history and configuration. The fresh [recovery verification](Phase4_Recovery_Verification.json) identifies the final checkpoint and exact restore result; its detailed report compares all 60 table digests, schema and archived files in a disposable recovery container. The first final restore exhausted the harness's RAM-backed filesystem on the 2 GB Docker VM. Recovery now uses its own anonymous disk volume, automatically removed with the disposable container; the working Compose data remains untouched. [Docker cleanup semantics](https://docs.docker.com/reference/cli/docker/container/run/#clean-up---rm) apply only to that container's anonymous volumes.

## Open completion gates

1. Confirm conflicting/unresolved metadata and combined-paper ranges, including the 80 queued association outcomes and the existing provenance-review record. Confirm actual question/answer document pairs.
2. Review original pages, correct unsupported/uncertain layouts and approve each independent quality dimension. All 181 candidate revisions remain unpublished and unpromoted; recorded live extraction reviews are zero.
3. Obtain actual current-scheme Final mock artifacts through official navigation or assisted import; the present announcements do not close that source gap.
4. Complete the 38 authentic paper/profile fixture gaps and record actual reviewer approvals. Facts-only practice PDFs must stay explicitly partial where no questions exist.
5. Resolve the carried [Phase 3 queue](Phase4_Continuation_Queue.md): required January 2026 P5 fallback edition, IBS guideline/supplement bindings, applicability/source reconciliation and descriptor readiness. New evidence belongs in a successor draft where necessary; pending taxonomy reviews cannot be treated as classification approval.

The acquisition/extraction mechanisms and recovery evidence are reviewable now. The unresolved gates remain visible rather than being represented as a completed or faithfully extracted live corpus.
