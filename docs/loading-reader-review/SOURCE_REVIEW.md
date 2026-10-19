# Published source rendering review

Read-only sampling of four current published questions; no corpus changes. Opened and visually inspected all eight PNGs listed in `source-render-measurements.json` using the image viewer.

| Sample | Full page | Optional crop | Observation |
|---|---|---|---|
| 1, Q11, page 15 | `source-1-full.png` | `source-1-crop.png` | Margin marker identifies 11(i); financial table stays legible. Published question provenance points at a suggested-answer page. |
| 2, c, page 7 | `source-2-full.png` | `source-2-crop.png` | Full page retains question 8 and all available options; crop follows the published option-C span and omits the surrounding question. |
| 3, d, page 26 | `source-3-full.png` | `source-3-crop.png` | Hindi source; full page retains its context. Existing span continues into later material, so optional crop also retains that material. |
| 4, c, page 19 | `source-4-full.png` | `source-4-crop.png` | Full page retains shared case and MCQ options; crop follows option C only. |

Full source pages are the safe default because the inherited corpus sometimes treats an answer option or solution as a question. Cropping is optional and uses recorded source line boundaries, with full-page fallback when coordinates are missing. It does not repair questionable publication boundaries. Green margin markers identify the recorded start without covering source text.

Measured on these four real published files: full-page cold renders 32.91–44.79 ms, warmed renders 0.19–0.28 ms. Optional crops took 15.83–36.07 ms cold and 0.19–0.24 ms warm. All warm PNGs matched cold bytes. These are renderer timings, excluding HTTP, database queries and client download; process-local LRU is bounded to 48 MiB. Authorization, current publication references, approved content-addressed path and file identity remain checked before serving cached content; changed file identities require SHA verification again.

Focused verification: `CAF_TEST_DATABASE_PORT=5443 uv run --no-sync pytest -q tests/test_published_pages.py` — 5 passed, including full-page dimensions and marker, recursive span coverage, conservative crop, bounded eviction, changed-file integrity, missing files/pages, binding and publication withdrawal.
