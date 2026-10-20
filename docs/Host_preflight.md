# Read-only home-host tools

`caf-host` currently provides `preflight`, `verify-bundle` and `inspect-backup`. Installation,
deployment, service/database status, encrypted recovery and rollback commands
remain later increments. Keep the `v0.2.0` release PR pending until the required
installation and recovery paths are verified.

## Host launcher

The Ubuntu launcher is `deploy/caf-host`, checked out with deployment tooling.
It runs Typer from a verified, locally loaded application image. Ubuntu needs
Docker and its standard OS commands; no separate Python installation or package
installation is required. Select an image containing the new `caf-host` entry:

```sh
CAF_HOST_IMAGE='<loaded-application-image>' sh /opt/caf/repo/deploy/caf-host preflight > preflight.json
CAF_HOST_IMAGE='<loaded-application-image>' sh /opt/caf/repo/deploy/caf-host verify-bundle /srv/caf/releases/<bundle>.tar.gz
CAF_HOST_IMAGE='<loaded-application-image>' sh /opt/caf/repo/deploy/caf-host inspect-backup /srv/caf/backups/<snapshot-directory>
```

The launcher resolves the selected image to its immutable image ID before
execution. The tool container runs as the invoking user's UID/GID, with no
network, a read-only image filesystem, dropped capabilities, no privilege
escalation and bounded CPU/memory/PID limits. It has no Docker socket, host root
filesystem, application-data or credentials mount. Docker commands run in the
host shell, outside the web application.

Preflight mounts only its private temporary probe directory. Bundle verification
mounts only the archive and its `.sha256` sidecar; it does not mount their parent
directory. The launcher derives the destination platform from `uname -m` and
accepts only `--allow-candidate` as an optional bundle flag. It never loads an
image, starts a service, extracts an archive or changes production storage.

## Report semantics

`preflight` emits JSON. Exit codes are:

| Code | Meaning |
| --- | --- |
| 0 | Automated probes completed without findings |
| 2 | Report produced, with warning or blocker findings |
| 1 | Collection/input/formatting failed; inspect stderr |

A successful automated inspection also leaves explicit manual verification
items in `unverified`. Production readiness additionally needs those recorded
acceptance checks, a verified external recovery copy and the installation gates.
The report is an observation, not permission to import production data.

Collected fields include OS/architecture, CPU threads, RAM, free space and
filesystem layout; Docker/Compose versions and container inventory; boot service
states; clock synchronization; Tailscale online state; listening TCP sockets;
readable firewall state; logind suspend policy; battery/AC and thermal-zone
readings; regular-login and greeter account records; and the exact external-drive
mountpoint. Initial installation requires at least 50 GiB free.

The collector bounds each command to 12 seconds. It never runs `sudo`. A denied
firewall read becomes `FIREWALL_UNVERIFIED`, rather than an assertion that the
firewall is safe or absent. The external drive must be mounted exactly at
`/mnt/caf-backup`; seeing the root filesystem is insufficient. This inspection
never writes a backup into an unmounted directory.

Tailscale login URLs, health errors, peer/user records, environment variables,
container commands/environment and credential files are excluded from output.
Private raw probes are temporary and can contain Tailscale metadata; do not
publish them. Their launcher-owned directory is removed on ordinary exit or
interruption. Keep saved reports owner-readable and outside Git.

SMART health, measured internet upload/download, reboot/unlock behavior, encrypted
backup writes/restores and real student HTTPS/Auth0 access remain explicit
unverified items. Battery/temperature readings do not prove low-battery shutdown,
charge limits or idle thermal behavior.

`verify-bundle` uses the exact shared format-1 verifier used by the release
builder. It checks outer/inner SHA-256 hashes, sizes, supported file membership,
regular files, duplicates, schema metadata, image references and platform.
Candidates require explicit opt-in. Invalid bundles exit 1; success emits the
verified manifest. Obtain archives/checksums from the accepted repository release
or owner-verified transfer; hashes alone do not establish the producer's identity.

## Inspect an existing backup before a restore

`inspect-backup` accepts a plain snapshot directory produced by the existing
`caf backup run` command. It checks the format-1 manifest, required protected
table inventory, dump SHA-256 and the exact archived file inventory and hashes.
It rejects unsafe paths, symlinks and special files. The launcher mounts only
that snapshot directory, read-only, into its constrained offline tool container.
It does not receive database credentials or a Docker socket and creates no files
inside the snapshot. Use an image built with this command; the candidate staged
on 20 October predates it.

Exit 0 emits a small JSON report containing the capture time, schema revision,
manifest/dump hashes and inventory sizes. It explicitly reports
`file_integrity_verified: true` and `restore_verified: false`. Exit 1 means
inspection failed; stderr describes the failure without echoing malformed
manifest values. Inspection never restores a database, tests ownership, validates
dump syntax or certifies the backup as recoverable. It can correctly accept a
hash-matching synthetic dump; only a subsequent isolated PostgreSQL restore can
establish restorability. Checksums alone also do not prove who created a backup.

The existing restore drill now uses the same file validator before starting its
disposable PostgreSQL container. It still compares restored row digests, schema
and migration baseline independently. That existing developer drill is separate
from this offline command; the packaged host restore workflow remains pending.
Encrypted snapshot packaging, external-drive handling and unattended recovery
are not implemented by `inspect-backup`.

## Verification on 19 October 2026

The collector was executed over SSH on the actual Ubuntu laptop without
installing software or changing services. The private snapshot was formatted
using the new packaged module on the Mac. The resulting report is saved on
Ubuntu at `/home/cafdeploy/caf-preflight-2026-10-19.json` with mode 0600, and a
matching ignored Mac copy is under `release-output/host-preflight-2026-10-19.json`.
This initial report has `tool_image: null` because formatting used the local uv
environment; a launcher-produced report records its selected image ID.

Observed: Ubuntu 26.04, amd64, 12 CPU threads, 15,937,683,456 bytes usable RAM,
414,255,108,096 bytes available storage, Tailscale online, synchronized clock and
enabled Docker/Tailscale/SSH boot services. Only two findings were emitted:
the deferred external drive and the unprivileged firewall read. No application
containers or production storage were created.

The visible `GDM Greeter` account was verified as `gdm-greeter`, with a runtime
home under `/run/gdm3`, the GDM group, and `/usr/sbin/nologin`. It is a login-screen
service identity; its runtime UID can change. The regular login users are the
owner account and `cafdeploy`; `caf-home` is the machine name. No account or GDM
settings were changed.

### Graphical login repair, 19 October 2026

Subsequent inspection found that the greeter was incorrectly running
`gnome-shell --mode=ubuntu`. The local `/etc/dconf/profile/gdm` contained
`user-db:user` and `system-db:local`, but omitted the packaged defaults database.
The owner logged into `rvabhi` on Ctrl+Alt+F3, backed up the profile to
`/etc/dconf/profile/gdm.before-login-fix`, appended
`file-db:/var/lib/gdm3/greeter-dconf-defaults`, and restarted `gdm` with sudo.
The owner confirmed that the normal graphical login worked again. Existing
local settings were preserved. This follows the resolved configuration diagnosis
in [Ubuntu issue 2143268](https://bugs.launchpad.net/ubuntu/+bug/2143268).
Do not append the line again if it is already present.

Focused verification:

```sh
uv sync --locked
uv run --no-sync caf-host --help
uv run --no-sync pytest -q deploy/tests
sh -n deploy/caf-host deploy/collect-host.sh
uv run --no-sync caf-host verify-bundle \
  release-output/caf-v0.1.0-candidate-becaeb736add-linux-arm64.tar.gz \
  --platform linux/arm64 --allow-candidate
```

Twenty-one tests passed, including redaction, non-login greeter classification,
missing/wrong backup mount, low space, stopped Tailscale, permission limitations,
probe timeout and the existing release-integrity guards. The saved older ARM64
candidate also passed the newly packaged verifier without a format change.
The image verifier now checks `caf-host --help`, and native Linux candidate builds
exercise the real host launcher using `scripts/verify_host_launcher.py`.

The local ARM64 image built from `01e801165e9bf8a97db74d22f3d92db557e122d0`
also passed the offline image checks, including the new console entry. Its ID is
`sha256:49021ada5c84b29f96d38c811493cfc750997b0a6f3143e161c35a0c1327d875`.
A constrained, read-only container replayed the real Ubuntu snapshot and matched
the uv-generated report exactly, apart from the expected `tool_image` identity.
Raw metadata was then deleted; only the non-secret reports remain.

The first Linux CI run passed 494 tests and exposed an existing immediate-volume-
cleanup assertion. The recovery test now waits up to five seconds for Docker's
asynchronous anonymous-volume removal, retaining its failure on a persistent
leak. A separate owned-volume write/cleanup probe passed locally. This adjustment
changes test timing only; it does not change the PostgreSQL sandbox or production
storage behavior.

[Linux verification run](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/39295554000)
passed for code revision `d679567577d8cce657be691263b3169c6d4b1ab6`: 495 Python
tests, 25 UI tests, frontend type checks/builds, Compose validation and release
version checks. The native amd64 image passed the real host launcher, offline
image checks, isolated application stack and checksummed bundle creation. This
does not deploy or activate an application on the Ubuntu laptop.
