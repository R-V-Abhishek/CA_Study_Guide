# Phase 0 verification — 2026-10-01

The acceptance gate passed using the existing Colima Docker context and disposable
PostgreSQL 16 containers. No production migration or corpus remediation was applied.

- Full isolated suite: **103 passed**, in both normal and changed module order.
- Dashboard, planning, and extraction checks also passed individually.
- Recovery tests covered protected records, snapshot consistency during and after
  source changes, timezone independence, dump/restore failures, missing tables,
  archive tampering, legacy manifests, and preservation of existing scratch databases.
- Normal database/admin/storage destinations and external acquisition were rejected.
- Frozen `0001_initial_schema` produces 42 application tables plus the Alembic
  revision table. Independent fresh/restore schema comparison reported no drift.
- Future contract models passed; authentication and reader endpoint enforcement
  remain later-phase work.

Verified recovery artifact:
[manifest](../data/backups/caf_20261001_135750_245563_ce8e08c1/manifest.json) and
[restore report](../data/backups/caf_20261001_135750_245563_ce8e08c1/verification_0313c3bcfba741e1bb74b90a4c42d841.json).
All 43 table counts/digests and 109 archived-file checksums match.

[Provenance and preservation report](../data/audits/20261001T140759.066952Z-beafc52b/baseline.json)
confirms every personal/published table remains unchanged against that checkpoint.
The [concise audit](../data/audits/20261001T140759.066952Z-beafc52b/baseline.md)
reports 191 confirmed synthetic documents, 34 suspected synthetic, 10 with authentic
sources identified, and 34 unresolved. It also records 196 missing source files,
1,056 current gradable units without paired answers, and 264 subtopics without
descriptors. These are diagnostic findings, preserved for later reviewed remediation.
Legacy reviewer identity remains unresolved.

The first checkpoint was retained with its failed verification report: timestamp
digests originally varied between the source's Asia/Kolkata setting and UTC restores.
The corrected checkpoint uses UTC-normalized digests. Container startup now waits
for TCP readiness; CLI logging resolves the current stream to avoid closed captures.
Existing backups were neither rotated nor deleted. Artifacts stay ignored by Git.

Only existing dependency deprecation warnings remain in the test output.
