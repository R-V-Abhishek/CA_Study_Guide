# Independent student classification review

OpenRouter outputs go to local JSON files and a Markdown review pack. These commands never import suggestions, publish labels, or modify the existing review queue. The API key belongs only in ignored `.env` as `OPENROUTER_API_KEY`.

```sh
uv run caf classify review models
uv run caf classify review export --output data/student_review/openrouter-batch.json
uv run caf classify review run --batch data/student_review/openrouter-batch.json --results data/student_review/openrouter-results
uv run caf classify review render --batch data/student_review/openrouter-batch.json --results data/student_review/openrouter-results --markdown data/student_review/QUESTIONS_AND_CLASSIFICATIONS.md
```

Export includes the latest nonfailed extraction per verified Final source document, including candidate extractions, and marks the batch experimental. `--reviewed-only` requires promoted/current reviewed extractions. `--revision` can explicitly select revisions; `--batch-source` can reuse an existing frozen batch without DB access. No extraction is promoted by exporting it. Every exported root retains all gradable parts, stems, available answers, source identity, and candidate descriptor evidence.

The provisional default is `nvidia/nemotron-3.5-super-vl:free`. On October 16, 2026, it was the newest model passing the live zero-price and JSON-schema capability checks; the former Qwen default no longer passed those checks. OpenRouter documents a 1M-token context and JSON-schema output support. A real two-part investment-property classification passed validation with reported usage cost zero (42,676 input tokens, 7,403 output tokens, 82.6 seconds); artifacts are under `data/student_review/openrouter-live-smoke-2026-10-16`. This verifies integration, not comparative accuracy. It has not been established as the most accurate model for this corpus. `models` fetches the live catalog and lists free schema-capable candidates newest first; recency is not an accuracy ranking. Compare separate frozen batches with `--model <id>:free`, using identical roots/taxonomy and independent student corrections. The report records actual and requested model IDs. Never compare accuracy against model-generated labels as ground truth.

Before any completion, the runner verifies the selected model's live zero prompt/completion/request prices, schema support, and expiration. Every request also enforces zero provider prices; paid models, random routers, and automatic paid fallbacks are disabled. It requires reported usage cost to be zero. Full context exceeding a conservative model bound fails rather than being truncated. Network, quota, malformed-output, unsupported-label and missing-part failures remain visible. A failure stops the batch, preserving completed roots; rerun the same command to resume. `--limit` bounds the number of new roots per invocation.

Response budgets scale with gradable-part count (minimum 8,192 tokens; 57,344 for a 104-part composite), reserving room for per-label evidence. Read timeouts scale with that allowance because the live 8K pilot already took 82.6 seconds; connection establishment remains capped at ten seconds. The runner checks the model and advertised provider context/completion limits before sending the request. Missing provider limits remain unknown; they are not interpreted as zero. This budget is an estimate, and any truncated response still fails validation without accepting partial mappings. Execution provenance records the requested output allowance.

Rendering includes every exported root, visibly marks missing/failed classifications, and provides per-part agreement/correction fields. Existing Markdown is never overwritten, protecting student edits. Generate a new path after further completions. Source content is fenced, and secrets are excluded from provenance. Student corrections are review evidence; the document does not automatically sign off or change the existing queue.

Current model references: [Nemotron 3.5 Super VL free](https://openrouter.ai/nvidia/nemotron-3.5-super-vl%3Afree), [live model catalog](https://openrouter.ai/api/v1/models), [zero-price provider routing](https://openrouter.ai/docs/guides/routing/provider-selection#max-price).

## Dedicated Luna paper workers

The user subsequently selected GPT-6 Luna workers, one per paper. Frozen inputs, full paper catalogs, PDF source locations, validated outputs and review Markdown live under `data/student_review/luna-papers`. Three worker slots run concurrently. Saved files are checkpoints, not a background scheduler.

`caf_l3.paper_workers.load_record` replaces the lexical shortlist with the pinned full paper catalog and assigns a new input hash. `save_result` validates every gradable part, supported label and evidence before saving. `render_paper` preserves existing Markdown and includes hash-verified original PDF page text cited by workers. These operations never import results into the queue.

Canonical `results-direct/<question_id>.json` files represent completed semantic proposals. Keep unfinished drafts outside that directory; `needs_review` means an assessed ambiguity or taxonomy gap, not inference still to be performed. Scope comes from the frozen index and batch, not a glob of result files. Preserve superseded proposals in correction history.

When the original source establishes the parent MCQ, classify extracted answer-choice fragments by that question's tested concept and explicitly note the extraction artifact. Alternative option text alone does not establish a different tested concept. Student review must still correct mistaken gradability or boundaries; source recovery and classification do not silently rewrite the frozen extraction.

P5's first expanded review is preserved under `P5-expanded`. Its 293 candidate leaves combine 32 existing textbook draft leaves with 261 proposed index leaves from the official September 2025 edition modules 2–4. Those PDFs explicitly list May/September 2026 and January 2027 applicability; their May 2027 applicability remains unverified. The canonical `P5-index-complete` catalog adds two missing Module 1 headings (concept of supply and cross-border service place of supply), bringing it to 295 leaves. Module 1's September 2026 front matter explicitly applies to May/November 2027. All proposed labels still require review and approval. `caf_l0.index_candidates.draft_candidates` derives stable IDs and pins PDF hashes/pages. Prior results remain preserved, and workers review the catalog delta before saving outputs with new input hashes. `P6-index-complete` includes these additions in its 3,300-candidate cross-paper catalog.

Source PDF covers revealed 571 roots incorrectly assigned to P1 and another 120 incorrectly assigned to P4 in the extraction inventory. The standalone packs correct these assignments using `P1-corrected`, `P4-corrected`, `P2-rerouted` through `P6-rerouted`, and `P5-from-P4` / `P6-from-P4`; original inputs and the database remain preserved. The combined report uses the final index-complete P5/P6 catalogs. It verifies that all 3,009 original root identities appear exactly once.

```sh
uv run caf classify review luna-status
uv run caf classify review luna-render --markdown data/student_review/LUNA_ALL_PAPERS.md
```

The combined renderer validates saved mappings, catalog hashes and cited PDF evidence before writing. It refuses incomplete coverage by default. `--allow-pending` explicitly creates an interim report with missing classifications marked; this cannot serve as completed classification or student sign-off. Choose a new output path to preserve any student edits.

The completed October 16 student pack is `data/student_review/QUESTIONS_AND_AI_CLASSIFICATIONS_2026-10-16.zip`. Its main Markdown contains all 3,009 extracted question records and 7,778 gradable parts, plus two alternative OpenRouter pilot proposals for an existing question. The archive includes all 94 original question-source PDFs, a source index, all 3,300 candidate taxonomy nodes and descriptors, the initial textbook-index reconciliation, and the earlier 120-question AI baseline as a separate comparison file. The reconciliation predates the experimental P5 additions; it is not a current taxonomy-gap count. Extract the archive before opening relative source links. Previous interim files remain preserved.

P4's required semantic QA covered all 444 flagged parts across 186 roots, followed by a broader check of 175 generic gap notes across 89 roots. Exact assigned part IDs and source pages are recorded in `P4-corrected/semantic-qa-progress.json` and the three `broader-qa-*-progress.json` ledgers. Supported concepts were remapped; genuine gaps retain specific reasons. Prior proposals remain in correction history. A final resident/nonresident scope check also corrected two parts in the 47-part trust case. Full-corpus validation checks mappings, input/catalog hashes and cited PDFs before rendering. These checks establish provenance and structural validity; student review still determines accuracy and approval.
