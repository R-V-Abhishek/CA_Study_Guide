# First installation

`deploy/caf-host install` installs a verified offline release and restores an
existing format-1 backup into **empty** application storage. `caf-host status`
reports the installed version, observed schema, running containers and readiness.
These are real host operations. They never mount the Docker socket into Python
tool containers. Ubuntu needs Docker/Compose, Bash, jq, flock and standard OS
utilities; it does not need a separate Python environment.

## Production prerequisites

Use an accepted non-candidate release and its matching deployment scripts. Keep
the accepted recovery artifact independently on the Mac, verify its restore, and
retain the original baseline. External-drive automation is still deferred; this
installer does not establish a backup schedule or encrypt artifacts.
Do not activate production while the separately stored recovery copy is missing.

Prepare `/srv/caf` owned by `cafdeploy`, and `/opt/caf/repo` with the accepted
deployment tooling. `/srv/caf/{data,postgres,backups}` must be absent or empty;
the installer creates these children. Production requires 50 GiB free. Its
ownership initialization is limited to the new application data/backup binds.
Personal home directories and other Docker projects are untouched.

The owner-authenticated `deploy/prepare-host.sh` handles the small OS setup. It
checks Ubuntu 26.04 and the unit syntax, creates missing `/srv/caf`, `/opt/caf`
and restricted `/etc/caf` directories, and installs/enables `caf.service` without
starting it. Unexpected existing owners/configuration are preserved for review.
If a private production environment file has been staged with authorization:

```sh
sudo bash /home/cafdeploy/caf-staging/production/setup/prepare-host.sh \
  --config /home/cafdeploy/caf-staging/production/compose.env
```

The boot unit has a condition on the activated Compose pointer, so it does
nothing before successful installation. No formatting or package installation
is performed by this script. The SSH account cannot perform this step without
the owner's sudo authentication.

The real mode-0600 `/etc/caf/compose.env` must be owned by `cafdeploy`. Populate
it from `deploy/host.env.example` with seven different random hexadecimal
passwords (at least 64 characters), real Auth0 settings and the assigned HTTPS
`*.ts.net` application URL. The installer obtains image references, architecture
and source revision from the verified release instead of trusting those values
in the environment file. Auth0 URL allowlists and Tailscale Serve are separate
host configuration steps; installation does not claim to validate real sign-in.

## Bootstrap and install

On the Mac, verify the trusted release before sending it to Ubuntu:

```sh
uv run --no-sync scripts/release_bundle.py verify /path/to/release.tar.gz --platform linux/amd64
```

Transfer that archive, its `.sha256` sidecar and the accepted backup snapshot
over Tailscale SSH into private staging directories. On Ubuntu, after this trusted
transfer, bootstrap the packaged tooling image without Python:

```sh
cd /path/to/private/release-staging
sha256sum -c release.tar.gz.sha256
set -o pipefail
tar -xOzf release.tar.gz images.tar | docker image load
export CAF_HOST_IMAGE=$(tar -xOzf release.tar.gz manifest.json | jq -er .application.reference)
sh /opt/caf/repo/deploy/caf-host install /path/to/private/release-staging/release.tar.gz \
  --backup /path/to/private/accepted-backup
sh /opt/caf/repo/deploy/caf-host status
```

Use the actual bundle basename in these commands. Run the bootstrap pipeline in
Bash. The installer rechecks all bundle hashes, platform and loaded image
identities before modifying application data. Canonical Compose credentials stay
in private files rather than shell arguments or terminal output. It pins the
effective services to immutable loaded image IDs, preserves literal dollar signs
in credentials, retains the release archive/checksum and records a receipt.

The installer then copies captured blobs and configuration evidence, initializes
PostgreSQL, restores the dump, compares **every** restored table digest and schema
and all copied file hashes, migrates, and applies explicit role grants. Captured
configuration evidence goes under `data/recovery-configs`; it does not overwrite
the reviewed configuration inside the release image. It does not rerun
classification or replace account IDs or personal records. It deletes copied
sessions/login transactions and revokes unconsumed invitations before startup.

Web and worker start only afterward. `/api/v1/ready` checks a database connection,
the expected Alembic head and readable/writable required document storage. The
response exposes only `ready` or a generic 503. Activation records
`/srv/caf/installation.json` and `/srv/caf/current-compose.json`.

After successful installation, the owner can install and enable `deploy/caf.service`
as a system unit. It starts the recorded Compose configuration under `cafdeploy`
after Docker/network startup. Docker's bounded logs and restart policies remain
in effect. Real reboot/Wi-Fi/unlock acceptance still needs testing on the laptop.

## Failures and recovery

The deployment lock rejects overlapping operations. Existing containers for the
selected project, an installation receipt, symlinked storage or nonempty data
cause refusal. Re-running installation cannot overwrite an existing instance.

After a restore or migration failure, serving containers are stopped and the
database/files are preserved. Read the private `releases/install-*/failure.json`
and `install.log`; the record identifies the failed phase. `status` reports an
incomplete installation. Do not delete the receipt, rerun install, downgrade the
database or restore over nonempty storage. Keep access closed, diagnose the
failure, and select a separate empty recovery destination. An automated
restore/rollback command is still pending; see the upgrade section below for
forward upgrades.

Status is intentionally explicit about unfinished monitoring: worker visibility
is container state. `backup` reports the latest scheduled snapshot (or
`not_configured` before one has run). This is not a
worker heartbeat or a backup-age dashboard.

## Upgrading an installed release

`deploy/caf-host upgrade BUNDLE` moves an **active** installation to a newer verified
release. Bootstrap the new tooling image exactly as for installation (load the
bundle's images, export `CAF_HOST_IMAGE`), then:

```sh
sh /opt/caf/repo/deploy/caf-host upgrade /path/to/new-release.tar.gz
sh /opt/caf/repo/deploy/caf-host status
```

Steps, each recorded in `releases/upgrade-*/upgrade.log`:

1. Verify the bundle, platform and checksums; refuse candidates without
   `--allow-candidate`, the same or an older version, a changed PostgreSQL image,
   and any live schema the new release's migration chain does not contain.
2. Render the new Compose file from the private environment file, pin it to the
   loaded image IDs, retain the bundle beside the previous ones.
3. Stop web and worker (PostgreSQL stays up), capture a **new recovery snapshot**
   with the installed release, and check its files, protected tables, schema and
   that it was taken after services stopped. A stale snapshot is rejected.
4. Run forward Alembic migrations and grants only if the schema differs.
5. Atomically switch `current-compose.json`, start web and worker, check
   readiness, the schema, and that the running web image is the verified one.
6. Merge a receipt that keeps the previous release, its directory and snapshot.

Failure handling: if nothing in the database changed, the previous release is
restarted and the pointer restored automatically. After a migration has started,
services stay **stopped**, nothing is downgraded, and `failure.json` names the
snapshot to restore into an empty destination. `.upgrade-in-progress` blocks
another attempt until the failure has been read.

Status of this tooling: the planning, snapshot-gating and receipt logic are
unit-tested (`deploy/tests/test_host_upgrade.py`), and the shell orchestration has
been run end to end by `scripts/verify_host_upgrade.py` (below) on a native Linux
VM (arm64) against synthetic data. That is a rehearsal, not production
acceptance: it has not run on `caf-home`, so treat the first production use as
unverified and take a fresh snapshot first.

## Scheduled recovery snapshots

`deploy/caf-host backup` creates a snapshot with the installed web image
(`caf-host _backup run`), checks file integrity and protected tables, keeps
7 daily, 4 weekly and 6 monthly snapshots (only directories with a manifest and a
canonical name are ever pruned), and writes `backups/status.json`. If
`/etc/caf/backup-recipient.txt` (a public `age` recipient) exists it also writes
`/srv/caf/encrypted-backups/<snapshot>.tar.gz.age` with a checksum and removes
encrypted copies for snapshots retention dropped. The private identity must stay
off this machine. Without a recipient the status says `not_configured`;
a missing `age` binary or an encryption error marks the run failed and raises the
`BACKUP_FAILED` alarm. Nothing here proves a database restore: status reports
`restore_verified: false` until you run an isolated restore drill.

The owner installs the schedule (not done automatically), together with the health watch below:

```sh
sudo /opt/caf/repo/deploy/install-units.sh
```

It first checks that the installed web image has the `_watch` and `_backup` commands (releases up to `v0.2.1`
do not, and it refuses to install until a newer release is running). It then copies the four units to `/etc/systemd/system`, checks them with `systemd-analyze verify`, reloads
systemd and enables `caf-backup.timer` and `caf-watch.timer`. It prints a note if the backup recipient or the
alert webhook is not configured yet.

Copying encrypted files off the machine (the Mac, an external drive) is still manual.
The web page `/curator/system` is read-only; it no longer creates snapshots.

## Health watch and alerts

`caf-host watch` (units `deploy/caf-watch.service` and `deploy/caf-watch.timer`, every hour) checks
three things: the loopback readiness endpoint, the intelligence worker heartbeat
(`backups/worker-heartbeat.json`, written every 30 seconds) and the scheduled snapshot status
(`backups/status.json`: failed, or no success within 48 hours). The decision and de-duplication state
(`backups/watch-state.json`) are produced inside the application image, so the host script only delivers:
one message when a problem appears, one when it clears and one reminder per day while it lasts.

Nothing is sent unless `/etc/caf/watch.env` (mode 0600) defines `CAF_WATCH_WEBHOOK_URL`, for example an
[ntfy](https://ntfy.sh) topic URL. Without it the script only prints to the journal. The check is skipped
while the deployment lock is held, because upgrades and restores stop services on purpose. A failed
delivery is logged but not retried: the state already records the alert, so check
`journalctl -u caf-watch` if a notification never arrives.

The units are not installed by the installer: run `deploy/install-units.sh` (see above). The watch script and
its decision logic are tested, and `scripts/verify_host_upgrade.py` runs the script against a live Docker host
(alert once, stay quiet, report recovery). The timers themselves have not run on `caf-home`.

Application logs are JSON lines in production (`CAF_ENV=production`) and readable text elsewhere. Every
API response carries `X-Request-ID` (a harmless caller-supplied value is kept, otherwise one is generated)
and every log line written during the request carries the same `request_id`. Access logs still drop
query strings on `/auth/` paths.

## Recovering remote access

If the server stops answering SSH (for example after the lid was closed, the laptop slept or Wi-Fi did not
come back), run this at its console:

```sh
sudo /opt/caf/repo/deploy/recover-access.sh           # read only: power, sleep policy, network, services
sudo /opt/caf/repo/deploy/recover-access.sh --apply   # restarts NetworkManager and tailscaled, enables ssh,
                                                      # makes Wi-Fi available before login, stops lid/idle suspend
```

It never touches Docker, the CAF services, application data or the Tailscale login. If `tailscale status` then
says `NeedsLogin`, sign in with `sudo tailscale up` and follow the URL it prints.

## Reboot acceptance

A normal reboot has not been tested on `caf-home`. After `recover-access.sh --apply` and with the machine
on AC power, run `sudo systemctl reboot` and do not log in at the console. From another device on the tailnet,
within about ten minutes:

1. `ssh caf-home uptime -p` answers (SSH and Tailscale came up without a login).
2. `ssh caf-home 'systemctl is-active caf docker'` prints `active` twice.
3. `curl -fsS https://<tailnet-host>/api/v1/ready` succeeds, then sign in and open a question and a PDF page.
4. `ssh caf-home 'systemctl list-timers caf-backup.timer caf-watch.timer --no-pager'` lists both timers.

Record the date and result in `docs/Deployment_verification_*.md`; until then reboot acceptance stays pending.

## Disposable verification

`scripts/verify_host_install.py` runs only on native Linux against newly created
test directories and uniquely named `caf-install-*` Compose projects. It uses a
real backup exported from the synthetic three-account stack, then exercises the
actual shell installer, readiness, personal-record preservation, session
invalidation, service restart, immutable receipt, repeat-install refusal,
nonempty storage protection, the operation lock and failed-restore containment.
No production credentials or data enter the test.

Explicit test projects with `--allow-candidate` require 8 GiB free; the normal
`caf` production project always requires 50 GiB. Test web ports use random
loopback ports. Cleanup removes only the newly created test project and its
owned temporary paths. The production installer preserves failed destinations.
The release builder runs this drill before publishing a native Linux bundle.

`scripts/verify_host_upgrade.py` extends this to the upgrade, backup and watch
scripts. On a disposable install it checks: an upgrade with a real migration
(0009 to 0010) that keeps every record, the previous release and its snapshot;
refusal of same-version and overlapping upgrades; a scheduled encrypted backup
with an authenticated decryption; `caf-host watch` alerting once, staying quiet
while the problem lasts, then reporting recovery; rollback of a release that
cannot start with the database untouched; and a same-schema upgrade afterwards.
The release builder runs it after the install drill. Running it found and fixed
four defects: image identity on newer Docker stores, the application-owned
backups directory being unreadable to the host scripts, the upgrade receipt
recording `snapshot` instead of the real directory name, and unstable dashboard
coverage ordering.

### Verified checkpoint

[Native Linux CI run 39451970866](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/39451970866)
passed at source `ff9d746cc89b82a66b8313fca1eda6ff101cf67d`: 525 Python
tests, frontend checks/build, production stack checks and amd64 bundle creation.
The real installer passed snapshot restoration, record/file comparisons,
copied-credential revocation, readiness and service restart. Repeat installation,
nonempty destinations and overlapping operations were refused. An invalid dump
left recovery state intact and serving containers stopped. All 50 focused
deployment tests also passed on the Mac.

The owner reported successful execution of `prepare-host.sh --config ...`:
directories and private configuration were installed, and `caf.service` was
enabled without starting application services. SSH verification on 21 October
confirmed the expected directory owners/modes, mode-0600 production configuration,
an enabled/inactive unit matching the staged file, no application containers and
379 GiB free. Production import, real
Auth0 sign-in, private HTTPS and the accepted corpus restore remain separate
acceptance gates. No production installation is claimed by this CI result.

The [initial recovery checkpoint](Initial_recovery_2026_10_21.md) records the
successful isolated restore of the actual adopted corpus on the Mac.
