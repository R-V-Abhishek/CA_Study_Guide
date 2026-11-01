# Home hosting

## Current checkpoint

Ubuntu `caf-home` now runs the verified `v0.2.1` release with web, worker and
PostgreSQL. Private HTTPS readiness and frontend access pass; all 94 published
PDFs passed hash/path checks and a real page rendered. The database image, schema,
baseline, taxonomy and personal records were preserved. Real study-account Auth0
sign-in and browser acceptance await the owner entering their credentials/MFA.

Read the [1 November deployment verification](Deployment_verification_2026_11_01.md)
for exact release/content/recovery identities, activation records, successful
isolated restore, encrypted Mac backup and remaining limits. The application is
available privately at <https://caf-home.tailf901d2.ts.net/>. External backup
storage and scheduled encrypted backups remain unfinished; a verified manual
recovery copy is retained separately on the Mac.

The links below are historical preparation checkpoints; their statements about
production not yet being installed describe the earlier checkpoint dates.

See [container verification](Home_hosting_verification.md) for the build source,
image identity, checks, and limitations of this checkpoint.
The [latest application checkpoint](Application_checkpoint_2026_10_18.md) records
the subsequent application review, migrations and verification before Compose work.
The [production Compose checkpoint](Production_compose.md) records the service
wiring and configuration checks. The [isolated stack verification](Production_stack_verification.md)
records successful local runtime checks with synthetic data.
See [application releases](Application_releases.md) for checksummed offline bundles,
Conventional Commit release PRs and GitHub Actions. Publication remains separate
from Ubuntu installation and activation.
The [read-only host tools](Host_preflight.md) add packaged preflight and bundle
verification plus offline inspection of existing backup snapshots; a private
inspection report has been saved on the Ubuntu laptop.
The [Ubuntu staging checkpoint](Ubuntu_staging_2026_10_20.md) records a verified
amd64 candidate transfer, image import and packaged tooling checks on the laptop.
No application services or production data have been installed.
The [first-install workflow](Host_installation.md) adds actual release loading,
empty-destination restore, migration, activation and host status commands. It is
separate from production activation. Its native Linux installation drill passed;
the owner has run the host directory/configuration and boot-unit setup, and SSH
verification passed. The [initial recovery checkpoint](Initial_recovery_2026_10_21.md)
records a successful isolated restore of the adopted corpus. Production acceptance
remains pending.
The [recovery encryption checkpoint](Recovery_encryption.md) records the encrypted
Mac copy, authenticated decryption test and remaining key-custody requirements.

The production Dockerfile packages Python 3.12, dependencies from `uv.lock`, both
interfaces built with pnpm 12.6.0 and its frozen lockfile, Tesseract English OCR,
and PostgreSQL 16 client tools. It runs as UID/GID 10001. The same image supports
the API, `caf intel worker`, and one-shot `caf`/Alembic commands.

Only explicit build inputs enter the Docker context. Local `.env` files, data,
Git history, dependencies, prebuilt interfaces, and operator artifacts are excluded.
The frontend receives its source revision as a build argument instead of needing
Git inside the container. Runtime credentials must be supplied separately.

## Image build and packaging verification

Run from the repository root on the Mac. Install Docker Buildx if absent:

```sh
brew install docker-buildx
```

Homebrew's plugin can be invoked directly without changing Docker configuration.
For a committed source checkout with no modified or untracked files:

```sh
test -z "$(git status --porcelain)" || { echo 'Commit/review changes first'; exit 1; }
CAF_REVISION=$(git rev-parse HEAD)
/opt/homebrew/bin/docker-buildx build \
  --platform linux/amd64 \
  --build-arg SOURCE_REVISION="$CAF_REVISION" \
  --load -t "caf:check-$CAF_REVISION" .
sh deploy/verify-image.sh "caf:check-$CAF_REVISION"
```

On other hosts, use `docker buildx` when the plugin is discoverable. Frontend
compilation uses the builder's native architecture; the Python runtime uses the
selected target architecture. The Dockerfile requires a nonempty source revision.

For packaging development only, use an explicitly marked working-tree identity:

```sh
/opt/homebrew/bin/docker-buildx build --platform linux/amd64 \
  --build-arg SOURCE_REVISION=working-tree --load -t caf:packaging-check .
sh deploy/verify-image.sh caf:packaging-check
```

The verification runs without networking, database access, credentials, host
mounts, or published ports. It checks non-root execution, both interfaces,
migrations, CLI and worker help, OCR, PostgreSQL 16 clients, writable storage, and
rejection of missing production authentication configuration. It does not verify
Auth0 login, database migrations, recovery, or an end-to-end application startup.

Do not deploy an image built from a dirty checkout as an application release.
Release identity, image checksums, dependency locks and schema compatibility are
recorded and checked by the [release bundle tooling](Application_releases.md).

## Pending incremental steps

1. Complete real study-account sign-in, browser reading, student onboarding and
   access from a separate device; verify a normal reboot.
2. Configure external recovery storage, daily encrypted backups, retention and
   monthly restore verification. Current manual snapshots do not provide daily coverage.
3. Implement a general existing-installation upgrade/rollback workflow and the
   remaining operational visibility/content-update tooling. The PDF repair used
   a recorded one-time same-schema activation; first-install must not be rerun
   against existing production storage.

Updating a Git branch alone must never activate an application release. Ubuntu
will load a verified image bundle built on the Mac rather than build dependencies.
