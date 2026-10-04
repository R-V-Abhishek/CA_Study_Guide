# caf-l1
L1 Acquisition: link discovery, robots evaluation, rate-limited fetching, blob store synchronization, and catalogue inference.

Phase 4 acquisition starts from the Phase 3 inventory:

```sh
uv run caf acquire inventory --paper s2023.P1 --limit 20
uv run caf acquire inventory --paper s2023.P1 --limit 20 --enqueue
uv run caf acquire fetch --limit 20 --dry-run
uv run caf acquire fetch --link-id 123 --limit 1
uv run caf acquire fetch --link-id 123 --refetch --limit 1
uv run caf acquire discover --source final-suggested-answers --dry-run
```

Inventory planning defaults to Final; `--level` permits a separate lower-level audit,
and `--include-older` includes older attempts/schemes. Enqueuing links never confirms
metadata or acquires a document. Failed downloads retain retry/manual outcomes; rerunning
fetch resumes eligible links. `--refetch` checks previously downloaded URLs for changed
bytes. New bytes create an artifact with `supersedes_document_id`; the old artifact is
retained until an administrator accepts the successor extraction.

HTTP and browser discovery record failed pages and explicit zero-document results.
Browser runs use fresh Playwright contexts. Install the Chromium runtime through the
existing Playwright environment when browser discovery reports it unavailable.

HTTP and manual imports share PDF/header, native-content and page-range validation.
Combined PDFs keep `paper_page_ranges`; they cannot be assigned to one paper from a
group filename. Content/navigation conflicts and uncertain course identity require
curation. Administrator confirmation requires a Final course and valid source identity;
undated model and identified IBS collections are permitted.

Content-addressed PDF storage deduplicates bytes. Every successful import preserves a
separate immutable JSON receipt in `blob_dir/acquisition/`, including original/final URL,
response metadata, hash, observed metadata, and previous artifact hash. The existing
recursive blob backup includes these receipts. Manual `.meta.toml` files may declare
`source_url`, `collection_id`, and `paper_page_ranges` alongside normal catalog fields.
Invalid directory imports report failures and exit unsuccessfully while preserving
successfully imported PDFs.

The Phase 4 source audit can run without opening the application database:

```sh
uv run python scripts/phase4_discovery.py
uv run python scripts/phase4_sources.py --inventory docs/Phase4_Acquisition_Inventory.json --limit 150
uv run python scripts/phase4_sources.py --inventory docs/Phase4_Acquisition_Inventory.json --limit 1 --refresh-metadata
uv run python scripts/phase4_discovery.py --browser-only --no-write-merged --output docs/Phase4_Mock_Browser_Audit.json
```

These scripts preserve the frozen original inventory. The supplemental inventory records
official navigation evidence and distinct course routing. Acquisition reports every source,
rechecks cached hashes/pages, downloads bounded current Final artifacts, and preserves prior
observations. Native identity checks use examination/title headings rather than transaction
dates in question bodies. Dates on undated model/IBS covers remain pending applicability
evidence. Acquisition and navigation receipts live within the recursively backed-up blob
store. `acquired` records still have pending metadata confirmation and human quality review;
combined documents require paper-specific ranges, and image-only sources require OCR.
