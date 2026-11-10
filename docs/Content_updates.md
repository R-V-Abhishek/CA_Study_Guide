# Content updates

New source PDFs reach production as **content snapshots**. A snapshot is an archive of official source PDFs,
their catalogue hints and their acquisition evidence, all addressed by SHA-256. It is a separate identity from
application releases and recovery snapshots. Extraction, classification and every human decision are made again
on production, with production IDs. A developer database or blob store is never copied into production.

Requires a release that includes the `content` Compose service (first planned release: v0.4.0). `caf-host
content` refuses to run on an older installation.

## What crosses, and what does not

| In the snapshot | Not in the snapshot |
|---|---|
| PDF bytes (`sources/<sha256>.pdf`) | Extraction revisions, units, blocks |
| Catalogue hints: level, scheme, attempt, paper, document role, series, part, title, collection, page ranges | Administrator confirmation (`catalog_status=confirmed`) |
| Acquisition receipts (`observations/<sha256>/*.json`) | Classification suggestions and decisions |
| Confirmed question → answer pairs, as hints only | Accounts, notes, progress or any personal data |
| The SHA-256 of a superseded earlier version | Any database row ID |

`manifest.json` lists every entry; `snapshot_id` is the SHA-256 of the canonical entries, and the archive is
reproducible: the same documents give the same bytes.

## Rules enforced on import

- The whole snapshot is verified before anything is written: outer checksum, every member's size and SHA-256,
  no links, extra or duplicate members, every PDF valid, `snapshot_id` recomputed.
- One transaction. Any failure (for example an unknown paper or document role, or a superseded source that is
  not installed) adds nothing.
- An existing document (same SHA-256) is **never changed**. The receipt lists it under `existing`, with any
  catalogue fields that differ from the snapshot, for an administrator to review.
- `provenance_status` is `verified` only when a bundled receipt records an HTTPS download of exactly those
  bytes from a host in `config/sources.toml` `pdf_hosts`. The builder refuses a document without such evidence,
  so manually imported PDFs cannot be published this way.
- Metadata is re-derived from the PDF with the normal content checks. A new document is `inferred` or
  `needs_curation`, never `confirmed`.
- A missing exam attempt is created **unverified**, as corpus acquisition did.
- Acquisition receipts are copied into the production blob store's `acquisition/` evidence, never overwritten.

## On the curating Mac

Acquire and check sources as usual (`caf acquire discover`, `caf acquire fetch`, curator Catalogue review), then
build a snapshot from their SHA-256s:

```sh
uv run caf content build --output-dir release-output/content --sha <sha256> --sha <sha256>
# or: --from-file shas.txt (one SHA-256 per line)
uv run caf content verify release-output/content/content-<id>.tar.gz
```

Copy the archive and its `.sha256` file privately to `caf-home`, for example into `/srv/caf/incoming/`.

## On caf-home

Each step needs the owner's authorization. Every command accepts `--root DIRECTORY` (default `/srv/caf`).

1. **Import.**

   ```sh
   sh /opt/caf/repo/deploy/caf-host content import /srv/caf/incoming/content-<id>.tar.gz
   ```

   It verifies the archive in a network-less container, takes a recovery snapshot with the normal backup flow
   (encrypted when a recipient is configured), waits for the deployment lock, imports in one transaction and
   writes a receipt to `/srv/caf/content/receipts/<snapshot_id>-<time>.json` and
   `/srv/caf/content/last-import.json`. Nightly retention keeps the pre-import snapshot named there until the
   next import. Services stay up; the import only adds rows and files. A failure writes `failure.json` in the
   private `content/import-*` directory and states whether any documents were added.

2. **Confirm metadata** in the curator **Catalogue** (administrator), and pair question and answer documents.
   Each new document's `metadata_evidence.content_snapshot.answer_sha256s` lists the pairs confirmed on the Mac.

3. **Extract** confirmed documents with verified provenance (OCR enabled; nothing is promoted):

   ```sh
   sh /opt/caf/repo/deploy/caf-host content extract --limit 1   # measure time and memory first
   sh /opt/caf/repo/deploy/caf-host content extract --doc <document id>
   ```

   The log is kept in `/srv/caf/content/extract-<time>.log`.

4. **Review and promote** each candidate in the curator **Extraction** page.

5. **Classify** against production:

   ```sh
   sh /opt/caf/repo/deploy/caf-host content classify-export --taxonomy <release> --revision <id> [--revision <id> ...] [--name <name>]
   ```

   The manifest is written to `/srv/caf/content/outbox/<name>.json`. Copy it to the Mac, run the classifier there
   (for example `uv run caf classify operator-run --batch <name>.json --output-dir results/`), copy the result
   directory back, then:

   ```sh
   sh /opt/caf/repo/deploy/caf-host content classify-import /srv/caf/incoming/<name>.json /srv/caf/incoming/results
   ```

   The import applies the existing checks: pinned extraction and taxonomy, stale-evidence detection and
   immutable suggestions.

6. **Review and publish** in the curator **Classification queue**. Model output never publishes on its own.

## Locks

`caf-host content` holds `/srv/caf/.content.lock` for its whole run, so imports, extraction and batches never
overlap. `caf-host upgrade` refuses to start while that lock is held. An import also takes the deployment lock
for its database step, waiting up to 10 minutes for the hourly watch or a backup.

## Limits

- Taxonomy changes, descriptor approvals and corrections are not part of a snapshot; make them in the curator UI.
- Orphan blobs or receipts can remain after a failed import (content-addressed and harmless).
- The host script is exercised by the native-Linux drill in the release builder (`scripts/verify_host_upgrade.py`,
  step 7). It has not yet run on `caf-home`.
