# Loading and reader corrections — 17 October 2026

## Changes

- Repeated context, taxonomy-node and leaf-scope work is reused within a single authenticated GET/HEAD transaction. Mutation sessions do not opt in. Queries avoid repeatedly transferring complete artifact inventories and unused score evidence. Account changes retain existing cancellation and cache-clearing protection.
- Textbook reference trees load when their tab opens. Extracted question rendering is a separate lazy-loaded bundle. Note autosaves invalidate relevant note searches rather than refetching the entire workspace.
- The question reader defaults to original source pages, loads later images near the viewport and offers enlargement, optional cropping and extracted text. Answers retain their explicit reveal action and availability states. Raw processing identifiers are in Content details; readable limitations remain visible.
- Source rasters use a bounded 48 MiB process-local cache; client blobs use an account/revision-scoped in-memory query cache. Publication authorization and approved file identity are checked before server cache hits. Authenticated HTTP content remains `no-store`; hashed public build assets use immutable caching and entry HTML revalidates.
- Unknown coverage-exclusion attempt IDs remain null in the importance contract and display as “Attempt not identified,” preserving incomplete evidence.
- Profile Preferences adds **Include Hindi questions**, off by default. Server-side filtering covers search, lists and direct question/page access. The additive `0009_question_language` migration was applied to the local database without changing personal study records.

## Verification

Read-only direct backend handler samples on the existing corpus, using independent sessions before/after (not browser load timings):

| Handler | Before | After | SQL queries before → after |
|---|---:|---:|---:|
| Today/dashboard | 29.768 s | 0.930 s | 180 → 45 |
| Papers | 22.105 s | 2.491 s | 153 → 41 |
| Syllabus tree | 5.938 s | 0.919 s | 38 → 25 |
| Topic detail | 5.763 s | 0.339 s | 46 → 16 |

These are single-machine observations, not latency guarantees. They precede the final omission of unused paper/tree score evidence and therefore do not quantify that additional change. [Profiling record](performance-measurements.json).

- Integrated Python suite: **83 passed**, 9 dependency/deprecation warnings, 17.82 seconds. Covers reader/publication permissions, source rendering/integrity, language opt-in and account isolation, intelligence/importance, Auth0 error handling, request cache transaction boundaries and taxonomy releases.
- `pnpm --dir web type-check`: passed, including browser test TypeScript.
- `pnpm --dir web build`: both applications passed.
- `pnpm --dir web test:ui`: 25 passed.
- `git diff --check`: passed. Existing unrelated work preserved.
- Isolated HTTP smoke: question and source image both 200; source page 29.88 ms cold and 7.34 ms warm; private `no-store` retained. [Measurements](http-reader-smoke.json).
- Read-only live importance response validation: 298 coverage exclusions, including 104 unknown attempt IDs, validates successfully. [Measurements](importance-validation.json).
- Default question listing: 2,494 results versus 3,009 with Hindi enabled; 515 detected Hindi entries excluded. First 20-item handler sample: 91 ms with filtering. [Measurements](question-list-measurements.json).
- Eight real source-page images were opened and inspected. Full-page raster work measured 33–45 ms cold and 0.19–0.28 ms warm, excluding database, HTTP and download. [Review](SOURCE_REVIEW.md), [contact sheet](source-contact-sheet.png), [measurements](source-render-measurements.json).

## Remaining limitations

These source images are rendered evidence, not application browser screenshots. The new reader/loading browser tests could not execute: Chromium fails at startup with the macOS Mach-port/bootstrap permission failure before assertions. The available interactive-browser service also fails to start. Desktop/mobile UI inspection and browser interaction acceptance remain incomplete.

Inherited publication provenance sometimes points at a suggested-answer page or a single MCQ option. Showing source pages preserves its surrounding context but does not repair that mapping. Cropping follows recorded boundaries and can omit relevant surrounding material; it stays optional and off by default. See the source review for specific examples. Hindi detection uses Devanagari script and Hindi-labelled source titles; unlabelled image-only Hindi may need source metadata correction.

The existing normal-Terminal app process was preserved. Restart it from that same Terminal to load the new backend, then refresh the UI. An agent-launched replacement previously lost host DNS access, so this verification deliberately did not replace the working normal-Terminal server.
