# Ubuntu deployment verification — 1 November 2026

## Release and activation

The published-PDF repair is merged in [PR #5](https://github.com/R-V-Abhishek/CA_Study_Guide/pull/5).
[PR #6](https://github.com/R-V-Abhishek/CA_Study_Guide/pull/6) accepts `v0.2.1`,
commit `8855f58a7e7945b27d87074e94ab8417d6b4849d`, for `linux/amd64`.
The accepted-tag publishing workflow passed and published the
[release bundle](https://github.com/R-V-Abhishek/CA_Study_Guide/releases/tag/v0.2.1).
Ubuntu activated it at `2026-11-01T04:48:19Z` (10:18 IST).

| Identity | Value |
| --- | --- |
| Bundle SHA-256 | `a1cec24827003cde3f535c2dd93cb0c16f88c0ae12d5e56ae3cc71fd0cd1ab5a` |
| Recorded application image config ID | `sha256:99f343e81377eb3c2407c703698c2e66681e6451a2d5130eeef91225833e7567` |
| Loaded application image ID | `sha256:1c96f020a1d23806bfea42bed43ff6be2d1a0a27ae1b2753305a66697f6007a1` |
| Retained running PostgreSQL image | `sha256:1e1b47f9d7658fa983676e80fc65edebfa0d28711de222cfe851826a4c352e39` |
| Schema | `0009_question_language` |
| Content baseline | `baseline-2026-10-16` |
| Content manifest hash | `c59e12cb4f9696adbcc4647b0775542693517aa23870e37edfca753497370973` |
| Taxonomy / attempt | Version 9 / `2027-05` |

The Docker archive verifier reconciled the image config ID with Ubuntu's loaded
containerd image identity. The new bundle's PostgreSQL image was loaded and
verified but deliberately not activated; the database container/image stayed
unchanged. The previous `v0.2.0` bundle and configuration remain retained.

The image maps `/app/data` to `/srv/caf/data`. Existing publication paths resolve
to their canonical persistent blobs without changing database rows or weakening
approved-path and SHA-256 validation. The image verifier rejects bundled local
data, and the native container regression reads and renders a generated PDF
using a legacy relative publication path.

The repair's [native CI run](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/41271819835)
passed 525 tests, frontend checks, image checks, the three-account synthetic
stack/worker checks, and bundle/install drills. The
[release-branch run](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/41272642564)
passed its application, version/lockfile, and frontend checks before acceptance;
its separate native candidate build and install drill also passed. The
[accepted-tag publishing run](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/41272877897)
independently gates publication of the actual release artifact.

This repair used a narrowly scoped application activation, retaining the current
PostgreSQL image and schema `0009_question_language`. It must reject any unexpected
runtime configuration or schema change. There was no database migration, downgrade,
baseline adoption, classification rerun, or database replacement.

Activation evidence is private on Ubuntu under
`/srv/caf/releases/pdf-upgrade-jw7NmFl9/`, with the active receipt at
`/srv/caf/installation.json` and effective configuration through
`/srv/caf/current-compose.json`. The non-secret receipt was copied to
`release-output/v0.2.1/ubuntu-deployment-receipt.json` on the Mac.

Two guards rejected earlier attempts before serving was reopened. The first
found an archived mode-0600 file unreadable by the operator UID. An operator-owned
mode-0700 staging copy resolved this without changing original permissions;
its manifest and complete inventory were reverified. The second found expected
image/revision changes in Compose's `x-application` / `x-runtime-env` template
extensions. The corrected comparison excludes only those identity fields as
well as their service equivalents. Every other setting must match.

The completed image validation was retained; the resume script rechecked its
bundle hash, pinned application identity and schema before runtime verification.
Exact operator scripts and rejection records are retained privately. The
executed resume script is
`/home/cafdeploy/caf-staging/production/resume-pdf-activation-2026-11-01.sh`, SHA-256
`41252269361ee14ecb17b2e5b5fc7ae357738497483a6a62c481c1396d344a21`.
It is a historical one-time procedure, not a generic upgrade command to rerun.

## Pre-activation recovery

With web and worker stopped, a one-shot application container captured a consistent
snapshot using the existing `caf_backup` role under `/srv/caf/.deployment.lock`:

- Snapshot: `caf_20261101_040811_767761_10665e43`.
- Manifest SHA-256: `df417d3479830818b92f15498d46037fbd6dba7b67ad0c402dcf1fc10eb7869c`.
- Dump size: 145,417,572 bytes.
- Isolated restore: all 76 table digests and 4,308 archived files matched; schema
  matched a fresh migration baseline, with drift `{}`.
- Isolation: internal Docker network, disposable PostgreSQL volume, no published
  ports, no live database mounts. Its containers/network/volume were removed.
- Host verification record:
  `/home/cafdeploy/caf-staging/production/restore-drill-tE0QvjQA/verification.json`.

The snapshot was streamed over SSH into an `age`-encrypted Mac copy. Authenticated
streaming decryption verified all 4,310 files (including dump and manifest) against
the manifest without extracting plaintext. Encrypted SHA-256:
`bb6dd818c873a480c4e99cd307652d109f5b4f4870f8c4e203b4de7e98b06808`.

Private Mac artifacts are under
`release-output/production-recovery/2026-11-01/`, including the encrypted archive,
checksum, decryption-verification record, restore-verification record, and exact
operator scripts. The directory is mode 0700 and ciphertext mode 0600. These
artifacts are ignored by Git. The recovery identity remains off Ubuntu; the owner
previously confirmed saving it in their password manager. The independently
retained initial baseline recovery copy is preserved.

## Operational checks

After activation these commands passed; they are not substitutes for actual
Auth0 sign-in:

```sh
ssh caf-home '/opt/caf/repo/deploy/caf-host status'
ssh caf-home 'docker compose --env-file /dev/null -p caf -f /srv/caf/current-compose.json ps'
curl --fail --silent --show-error https://caf-home.tailf901d2.ts.net/api/v1/ready
```

The expected readiness body is `{"status":"ready"}`. A 502 means the private
proxy cannot reach the backend; check serving-container state and private logs
before restarting anything. The earlier maintenance 502 was caused by deliberately
stopping web and worker after discovering the PDF path mismatch.

Production acceptance checks completed:

- Live database still matched all 76 pre-activation table digests and schema.
- All 94 actual published PDFs passed approved-path and SHA-256 checks; an actual
  source page rendered to PNG. Baseline, manifest, taxonomy and attempt identities
  matched those above. No publication paths were rewritten.
- Auth0 discovery succeeded from the actual application container. Browser sign-in
  reached the expected Auth0 tenant and application; account authentication awaits
  the owner entering their existing credentials/MFA.
- Private HTTPS readiness returned `{"status":"ready"}`; frontend HTTP 200;
  certificate verification succeeded; anonymous question access returned HTTP 401.
- A same-network Mac frontend request took 0.068263 seconds. This is not a remote
  internet performance measurement.
- Web/worker run as UID/GID 10001, read-only root, capabilities dropped, zero
  restart counts. Web publishes only `127.0.0.1:8788`; PostgreSQL publishes no port.
- Worker was running; its single existing job was `ok`, with no failed jobs.
  Monitoring currently covers container state, not a dedicated heartbeat.
- Existing owner records: one note and four progress rows. Storage: 359 GiB free.
- Tailscale Serve remains private HTTPS to loopback; no Funnel configuration.

Host status reports `backup: "not_configured"` because scheduled host backup
tooling is unfinished. This does not describe the independently verified manual
recovery snapshot recorded above.

Keep the previous immutable image, bundle, installation receipt, and Compose file.
An application rollback must support the existing schema. Database restoration is
a separate recovery action that can discard newer activity; never rerun first
installation against existing data or silently restore a developer database.

## Remaining acceptance work

- Complete real study-account Auth0 sign-in and browser reading acceptance.
- Invite the other students and restrict their tailnet access to application HTTPS.
- Verify a normal reboot and access from a separate student device; same-network
  Mac timing is not a remote ISP performance measurement.
- External backup drive, scheduled encrypted backups/retention, and monthly restore
  automation remain pending. This manual snapshot does not establish daily coverage.
- General `caf-host deploy`, application rollback/recovery commands, detailed
  operational visibility, and remaining home-hosting plan items are not completed
  merely by this repair.
