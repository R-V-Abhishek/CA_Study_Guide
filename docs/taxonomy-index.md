# Contents-based taxonomy review

Generate a review draft from the locally downloaded module front-matter PDFs:

```sh
uv run caf taxonomy-index draft --manifest taxonomy/textbook_v1/manifest.json --output /tmp/taxonomy-index-review.json
```

Artifact paths resolve from the current directory; use `--base-path` for another
repository root. The command preserves existing output files. It does not access
the database, change the source manifest, or approve/publish taxonomy nodes.

Automatic extraction starts at **Detailed Contents**, then reads the remainder of
each front-matter PDF. If that heading is absent, extraction starts at the first
standalone **Contents** heading. For unusual layouts, repeat `--pdf-page` with
explicit 1-based PDF pages. Explicit page selection applies to every front-matter
source in the supplied manifest, so use a manifest containing only the intended
source when selecting its pages manually.

The JSON report contains source hashes, download URLs, selected PDF pages, draft
parent-child relationships, printed page references, and unresolved source lines.
Printed references such as `3.72` are textbook labels, not PDF offsets. Numbered
sections are attached to observed chapter/unit or numbered prefixes. Unnumbered
and ambiguous content is retained for curator review rather than invented.

Reconciliation compares normalized names and the full parent path against current
draft nodes. `missing_from_draft` means no matching kind/name was found; spelling
or wording differences can cause this result. A matching title in another path is
flagged for hierarchy review. Multiple matches remain ambiguous. Every result
requires source review before a curator changes or approves the taxonomy.
