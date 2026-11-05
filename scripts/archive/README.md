# Archived phase scripts

One-off scripts from the phased build-out (phases 2 to 7). Nothing in the repository, CI or the
documentation invokes them, and they are not maintained: they may no longer match the current
schema or APIs. Kept for history and as a record of how the early corpus work was done.

Run one only after reading it. Paths that assume the scripts live in `scripts/` (for example
`Path(__file__).parents[1]`) now need one more parent. Anything still needed day to day should be
moved back to `scripts/` and covered by a test.

Some of them import helpers that stayed in `scripts/` (`phase2_migration_drill`, `phase3_prepare`); run those with
`PYTHONPATH=scripts`.
