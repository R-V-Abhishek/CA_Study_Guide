# Independent draft-source review

The first automated draft was independently reviewed before import. The review found truncated multiline headings, running headers emitted as concepts, worked-example titles, exercise pages included in source spans, and internal textbook units absent from ancestry. These defects prevented source approval and classifier eligibility.

Concrete checks included AFM's Adjusted Present Value section extending into `TEST YOUR KNOWLEDGE`, an AFM `Example:` leaf, incomplete Financial Reporting headings ending in `INTRODUCTION OF`, repeated `DIRECT TAX LAWS` running headers, and Financial Reporting framework units missing from the tree. The extraction repair joins adjacent display headings, excludes running headers and examples, caps conceptual spans before exercises, and adds official internal units. Exclusions remain recorded in the artifact reconciliation audit. Allocated IDs remain in the identity registry even when an invalid candidate is removed.

The current P1–P3 source files were subsequently refreshed following ICAI's ongoing official applicability, so the initial review is evidence about failure modes, not approval of the replacement files. Machine descriptors retain edition, instruments, page spans and unresolved source issues. A recorded issue blocks approval until a reviewer checks the textbook and creates a corrected revision.

No machine generation, downloaded-file verification, browser test or independent agent review constitutes an authenticated student's descriptor approval or an administrator's structural release approval. Complete contents/outline/body reconciliation and substantive classification-boundary review remain explicit release gates.

Visual QA also rendered the replacement AFM chapter and FR colophon with `uv run scripts/phase3_visual_check.py`. AFM's APV concept ends on PDF page 41; the exercise section begins on page 42, outside its repaired source span. The FR colophon on PDF page 2 visibly records the November 2024 edition and August 2025 reprint. The reproducible inspection writes images and a bounded inspection manifest under `/tmp/phase3-pdf-check`; these temporary images are not release approvals.
