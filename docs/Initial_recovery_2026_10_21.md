# Initial recovery checkpoint — 21 October 2026

The actual local database has schema `0009_question_language` and the active
`baseline-2026-10-16` adoption. No classification or baseline adoption was rerun.
The existing backup implementation captured a consistent database snapshot and
the required document/configuration files into private, Git-ignored Mac storage.
The original pre-baseline backup was preserved.

| Evidence | Value |
| --- | --- |
| Snapshot | `caf_20261021_133141_258156_7f206242` |
| Manifest SHA-256 | `017b9ac533233cf58190916ad29e2c835b0c3e8c54414ef4f665ce7a57f242e1` |
| Database dump | 145,401,304 bytes |
| Archived sources | 3,911 files |
| Archived configuration | 406 files |
| Restored tables | 76, all digests matched |
| Schema | Matched both captured schema and migration baseline |
| Archived files | All 4,317 hashes matched |

Private artifacts are under `release-output/initial-recovery/`; the snapshot path
is recorded in `latest-snapshot.txt`. The successful report is
`verification_79bc72214d5d45b6b3f5c52a96281ac7.json` inside the snapshot.
These files contain personal data and are not release artifacts or Git inputs.

`create_backup()` ran without an operational session, so it did not write a
backup event into the source database. `inspect_recovery_files()` checked all
captured bytes, and `verify_backup()` restored into a new disposable PostgreSQL
16 container and compared every table digest, schema and archived file. The
manifest includes the existing account IDs, personal records, classifications,
publication state and history. All five pre-existing Mac containers survived.

The first drill failed because Colima did not forward its new loopback port to
the Mac. A second drill used a temporary SSH tunnel through Colima's existing
SSH configuration, forwarding Mac `127.0.0.1:55429` to VM `127.0.0.1:55429`.
`PostgresSandbox` was given that fixed published port for this invocation only.
The successful drill removed its owned container/volume and tunnel. No Docker
daemon settings, source records or application configuration were changed.
The unsuccessful report remains alongside the successful report for diagnosis.

This is a verified Mac recovery copy, not a scheduled or encrypted backup system.
Encryption/key custody, the external drive and retention automation remain
pending. The snapshot has not been imported into Ubuntu, and no production
service is running there. It represents the capture time, not later Mac activity;
take a final verified snapshot during the eventual cutover window.

## Ubuntu staging

The tested candidate from [CI run 39451970866](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/39451970866)
was downloaded, fully verified on the Mac, transferred over Tailscale SSH and
checked again on Ubuntu. The artifact is
`caf-v0.1.0-candidate-ff9d746cc89b-linux-amd64.tar.gz`; its source is
`ff9d746cc89b82a66b8313fca1eda6ff101cf67d`. It remains a candidate.

Ubuntu staging is `/home/cafdeploy/caf-staging/ff9d746cc89b/`, with matching
deployment scripts from that exact Git revision under `tooling/deploy/`.
The transferred checksum and packaged `verify-bundle --allow-candidate` passed;
`host-verified-manifest.json` records the verified release. Both offline images
were loaded. `verify-image.sh` passed the non-root Python, interfaces, migrations,
CLI/worker, OCR, PostgreSQL client and production-auth configuration checks.
`caf-host status` returned `not_installed` with exit 2 as expected. No containers
remained after verification. Production data was not transferred.
