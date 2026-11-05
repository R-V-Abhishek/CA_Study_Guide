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
- Auth0 discovery succeeded from the actual application container. The owner then
  completed real study-account sign-in through the expected Auth0 tenant, and the
  authenticated study workspace loaded with existing personal activity.
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

### Signed-in browser acceptance

After the owner completed Auth0 sign-in, the existing authenticated browser tab
passed these read-only checks on 1 November:

- Today loaded the May 2027 planning target and existing personal activity.
- Questions loaded a catalog of 2,494 reviewed questions.
- Financial Reporting, September 2025 RTP, Q19
  (`0159ce76b41c3694958fb459e8b2d5e7296ecb3af6e1dac399b4df7a571d1fa9`)
  opened with the expected question and quality indicators.
- Original question pages loaded, including source page 13; the actual PDF page
  was visually readable in the Source and pages viewer.
- Reveal answer loaded original answer pages 29 and 30.
- Extracted text displayed the shared stem, question parts and answer text.
- Existing warnings remained visible: missing marks/choice review, source boundary
  review, May 2027 applicability review pending, and zero student topic-label
  verifications. This check does not certify unresolved content quality.

No notes, progress, classifications, publications or account settings were edited.
The authenticated tab was left available to the owner. These checks do not cover
logout, invitation/revocation, account disabling or real three-student concurrency.

Keep the previous immutable image, bundle, installation receipt, and Compose file.
An application rollback must support the existing schema. Database restoration is
a separate recovery action that can discard newer activity; never rerun first
installation against existing data or silently restore a developer database.

## Remaining acceptance work

- Complete logout/account-disable and invitation/revocation acceptance; verify
  real three-student production concurrency separately from synthetic CI coverage.
- Invite the other students and restrict their tailnet access to application HTTPS.
- Verify a normal reboot and access from a separate student device; same-network
  Mac timing is not a remote ISP performance measurement.
- External backup drive, scheduled encrypted backups/retention, and monthly restore
  automation remain pending. This manual snapshot does not establish daily coverage.
- General `caf-host deploy`, application rollback/recovery commands, detailed
  operational visibility, and remaining home-hosting plan items are not completed
  merely by this repair.

## Reboot acceptance, 2026-11-04 (release v0.2.3)

The owner issued a normal `systemctl reboot` and did not log in at the console. Checked from the Mac over
the tailnet about 13 hours later:

- `boot_id` changed from `8fa8d514-9c5e-4d36-a47a-15d1efca004d` to `d215cc96-d0f5-40b1-a7d4-c821ec3aafd3`.
- `caf`, `docker`, `ssh` and `tailscaled` were active and enabled. There were no failed units.
- `caf-db-1` and `caf-web-1` were healthy, and `caf-worker-1` was up.
- `/api/v1/ready` returned 200 on host loopback and at the tailnet HTTPS URL.
- `caf-watch.timer` had run on schedule, and `caf-backup.timer` was scheduled for 03:30.
- The only console session was the GDM greeter, so no login was needed.

The check was delayed, not the server: the administrator Mac's Tailscale client could not reach the control
plane while a managed Cloudflare WARP profile was connected (see "Recovering remote access" in
`docs/Host_installation.md`). A signed-in browser check after the reboot is still pending.

## Upgrade to v0.2.4, 2026-11-05

v0.2.4 (commit `375fd612d7b89b06428909beb239b86413c62137`) adds the retention rule from PR #24: a backup never
prunes a snapshot that the installation receipt names as a rollback point.

- The release bundle `caf-v0.2.4-linux-amd64.tar.gz` passed its sha256 check on `caf-home`. Its manifest named
  the same commit and required schema `0010_bounds_and_indexes`, which is the running schema, so no migration ran.
- The host checkout `/opt/caf/repo` moved to tag `v0.2.4`. Its scripts run the upgrade and the
  `caf-backup`/`caf-watch` timers, and the protection is passed to the image by `deploy/backup-host.sh`.
- `caf-host upgrade` finished at 04:40 UTC and kept the v0.2.3 release and its snapshot
  `caf_20261105_043955_381368_108ebee3`. Web and worker run image `sha256:efa495f9…`; `caf-db-1` was not
  restarted. `/api/v1/ready` returned 200 on host loopback.
- A manual `caf-host backup` immediately afterwards created `caf_20261105_044138_121833_ced77b68`, kept the
  v0.2.3 rollback snapshot from the same day, and deleted nothing. Retained: `caf_20261101_040811…`,
  `caf_20261104_220045…`, `caf_20261105_043955…` and `caf_20261105_044138…`.

Limitation: the v0.2.1 rollback snapshot `caf_20261104_023044_121929_b5b2aa20` was deleted on 2026-11-04 by the
retention rule in place before this fix (a newer snapshot from the same day replaced it). The receipt still
names it under `previous`. The oldest remaining point at schema `0009` is the install snapshot
`caf_20261101_040811…`.

Signed-in browser check (v0.2.4, after the reboot): the owner signed in through Auth0 at the tailnet HTTPS URL.
The question catalog listed 2494 reviewed questions. Question
`001d2efaf53e…` (Financial Reporting, Sept 2025 RTP, Q11) opened with its original PDF source pages 15–16
rendered, and its extracted text and answer revealed. Every signed-in API and page-raster request returned 200.
Tailscale key expiry for `caf-home` was disabled in the admin console the same day ("No expiry").

### Encrypted nightly backups, 2026-11-05

- The owner installed `age` 1.2.1 and `/etc/caf/backup-recipient.txt` (root:cafdeploy, 0644). It is the public
  recipient of the Mac recovery identity (`age-keygen -y` of the identity matches it); the identity stays on the Mac.
- `caf-host backup` created `caf_20261105_045507_248467_f6e241f6` and its encrypted copy in
  `/srv/caf/encrypted-backups/`; status `encryption: encrypted`. Retention deleted only the unprotected manual
  snapshot `caf_20261105_044138…` and kept the protected v0.2.3 rollback snapshot.
- On the Mac: the ciphertext passed its sha256 check in `release-output/nightly-encrypted/` (0700/0600) and
  decrypted with the recovery identity. Its archive held only that snapshot directory, the manifest sha256
  (`29089954…`) matched the server status, and `caf-host inspect-backup` passed (76 tables, 4308 files). The
  decrypted copy was deleted afterwards. No database restore drill was run on this copy.

Still pending: an automatic off-host copy (the Mac copy above is manual) and the external drive.
