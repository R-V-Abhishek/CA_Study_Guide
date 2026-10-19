# Read-only home-host tools

`caf-host` currently provides `preflight` and `verify-bundle`. Installation,
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
