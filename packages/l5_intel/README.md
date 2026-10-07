# caf-l5
L5 Intelligence: exam and practice scoring, recency decay, subtopic importance, and Depth Gate metrics.

Phase 6 resolves profile → target attempt → explicitly reviewed taxonomy binding
→ canonical scoring configuration → successful snapshot for that exact context.
A draft rebuilt release prevents fallback to generated legacy guidance. Approved,
active and archived releases remain selectable through reviewed bindings.
Unresolved version-specific applicability is exposed and excluded from scope.

Recomputation uses PostgreSQL jobs and repeatable-read inputs. Pending requests
coalesce by attempt, taxonomy and configuration. Workers claim retryable leases;
only the current, unexpired owner can promote output. A result computed from an
older corpus generation remains stored but cannot replace the current snapshot.
Publication and ledger mutations invalidate existing contexts transactionally;
the worker discovers newly approved bindings and supplies their initial config.

```sh
uv run caf intel enqueue --target-attempt 2027-05 --taxonomy-version 3
uv run caf intel worker --once
uv run caf intel status --target-attempt 2027-05 --taxonomy-version 3
uv run caf intel why NODE_ID --target-attempt 2027-05 --taxonomy-version 3
uv run caf intel backfill-reader
uv run caf intel seed-coverage --taxonomy-version 3
```

`seed-coverage` imports observed acquisition counts and Phase 4 continuation
reasons, preserving existing reviewed rows. Expected inventory stays unknown;
it creates no review, applicability or official-scope approval. Exam eligibility
requires reviewed question-bearing source slots and all gradable regions, rather
than optional marks summing to a paper maximum. Missing answers alone do not
invalidate a complete question paper. Exam frequency uses usable attempts strictly
before the target. Dated practice at the target month uses age zero; undated and
later practice remains outside decay scoring.

Official priors require a reviewed actor and a source object containing
`kind="official_weightage"`, `taxonomy_version_id`, `document_sha256` and
`official_url` (HTTPS on an ICAI domain). The hash must identify an acquired,
verified, confirmed Final `weightage` document. Generated and unbound priors do
not qualify. Missing components remain null, weights stay configured, and the
known weighted subtotal is displayed separately. Explanations read persisted
normalized components and occurrence contributions.

Without full historical importance for selected papers, plans use reviewed
syllabus order, prioritizing genuinely in-progress work. Budgets and chapter
caps apply to both modes. Personal progress is unweighted when reviewed priors
are unavailable, and is separate from corpus completeness.
