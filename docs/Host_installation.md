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
restore/upgrade/rollback command is still pending.

Status is intentionally explicit about unfinished monitoring: worker visibility
is container state, and backup scheduling is `not_configured`. This is not a
worker heartbeat or a backup-age dashboard.

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
