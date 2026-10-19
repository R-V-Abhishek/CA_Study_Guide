# Home hosting

## Current checkpoint

Ubuntu remote access, firewall, AC power configuration, Docker Engine, Compose,
and Buildx have been verified. No application or production database is deployed.
External recovery storage is deferred; production import remains pending.

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
Base image digests, release identity, image checksums, and migration compatibility
must be recorded by the future release bundle tooling before production use.

## Pending incremental steps

1. Implement and verify host deployment checks and recovery tooling using the
   checksummed release bundles.
2. Configure Auth0 and private HTTPS, then test an isolated restore.
3. Import production data only after a verified separately stored recovery backup.

Updating a Git branch alone must never activate an application release. Ubuntu
will load a verified image bundle built on the Mac rather than build dependencies.
