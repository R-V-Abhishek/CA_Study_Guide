# Production Compose checkpoint — 18 October 2026

`compose.production.yml` is independent of the developer `docker-compose.yml`.
It consumes an already loaded application image and does not build on Ubuntu.
Configuration and an isolated local stack have been verified. See the
[runtime verification record](Production_stack_verification.md) for evidence and limits.
No production stack has been installed on Ubuntu.

## Services and boundaries

| Service | Purpose | CPU / memory limit | Access |
| --- | --- | --- | --- |
| `db` | PostgreSQL 16 | 2 CPUs / 3 GiB | Internal network only; no host port |
| `web` | One Uvicorn process, API and both interfaces | 2 CPUs / 2 GiB | `127.0.0.1:8788`; outbound access for Auth0 |
| `worker` | One existing intelligence worker | 1 CPU / 2 GiB | Internal network; operations database role only |
| `admin` | Explicit migration/grant commands | 1 CPU / 1 GiB | Manual `tools` profile; administration credentials |
| `pipeline` | Explicit acquisition/processing commands | 2 CPUs / 3 GiB | Manual `tools` profile; pipeline and operations roles |

These are initial budgets, not measured capacity guarantees. Run at most one
expensive pipeline command at a time. Compose does not enforce a global lock on
multiple `run` invocations; the deployment command interface must add that lock.

The application services use UID/GID 10001, a read-only image filesystem, dropped
capabilities, no privilege escalation, a bounded temporary directory, and bounded
JSON logs (three 10 MB files per container). Web/worker/database restart unless
explicitly stopped. Manual tools exit after their selected command.

Persistent host paths are `/srv/caf/data`, `/srv/caf/postgres` and `/srv/caf/backups`. Compose refuses
to create missing source directories automatically. Host preparation must create
the data and local backup directories with ownership suitable for UID/GID 10001 before startup.
PostgreSQL uses its image's normal entrypoint to initialize database ownership.
No host Docker socket, repository checkout, or `/etc/caf` directory is mounted.
The local backup path is mounted at `/srv/caf/data/backups` inside application
containers to match the existing runtime settings while keeping backups in the
planned separate host directory. This is temporary local recovery storage, not
the deferred external backup drive.

Web gets the existing serving-role URLs, including the backup read role required
by the current API lifespan. It receives no administrator or pipeline password.
The worker receives only its operations-role URL. Administrative credentials stay
in the separate manual service. Both AI-provider keys are explicitly empty in
all application containers; this checkpoint does not enable model calls.

## Configuration

`deploy/host.env.example` lists required inputs without credentials. The actual
file will live at `/etc/caf/compose.env` with mode 0600, outside Git.

- Select a verified, loaded release image and its Git commit. Application images
  have `pull_policy: never`; missing images must fail rather than trigger a pull.
- Use seven distinct randomly generated hexadecimal database passwords, each at
  least 32 bytes. The URLs are assembled from these same passwords, so arbitrary
  special-character passwords require URL encoding before this wiring can support
  them. Empty values fail Compose validation; uniqueness/format and release
  compatibility checks belong in the upcoming host command interface.
- Supply the private HTTPS URL without a trailing slash, plus the Auth0 issuer,
  client ID and client secret. The callback derives as `<URL>/auth/callback`.
- Keep the real configuration restricted: rendered `docker compose config`
  output includes credentials. Operators should use `config -q` for validation.
- Default architecture is `linux/amd64`; select a matching image/platform for
  different replacement hardware. Set `CAF_POSTGRES_IMAGE` from the verified
  bundle manifest to select its exact bundled PostgreSQL image. The standalone
  default remains `postgres:16-bookworm` for configuration/integration checks.

## Verified configuration checks

Run from the repository root:

```sh
uv run --no-sync scripts/verify_production_compose.py
```

Verified on Mac Compose 5.5.1. Expected output:

```text
PASS: service isolation, loopback port, role wiring, limits, manual tools, and 13 required-value failures
```

The verifier invokes the real Compose parser with dummy values, an explicit empty
env file, and a restricted environment. It checks the three default services, five
services with tools enabled, role/password consistency, mounts, network/port
boundaries, non-root execution, resource/log limits, disabled AI keys and every
required input's empty-value failure. It neither contacts a Docker daemon nor
starts containers, and it does not load the local application's `.env`.

## Explicit startup sequence

These describe the intended manual sequence after storage and configuration are
prepared. Migrations, grants and startup were exercised together by the isolated
test harness with synthetic data; the Ubuntu paths and credentials remain untested:

```sh
docker compose --env-file /etc/caf/compose.env -f /opt/caf/repo/compose.production.yml config -q
docker compose --env-file /etc/caf/compose.env -f /opt/caf/repo/compose.production.yml up -d db
docker compose --env-file /etc/caf/compose.env -f /opt/caf/repo/compose.production.yml run --rm admin db migrate
docker compose --env-file /etc/caf/compose.env -f /opt/caf/repo/compose.production.yml run --rm admin db grants
docker compose --env-file /etc/caf/compose.env -f /opt/caf/repo/compose.production.yml up -d web worker
```

An explicit tool command, for example `run --rm pipeline extract --help`, selects
the manual service without running the other tools. Pipeline outputs must use
the mounted data directory, because files baked into the image are read-only.
Taxonomy activation and other commands requiring broader privileges remain
explicit administrator operations; the pipeline role's permissions are retained.

Do not use the above sequence as a production upgrade procedure. Backup,
maintenance mode, compatibility checks, locking and receipts are not implemented
yet. There are no automatic migrations during normal startup or restart. The web
healthcheck measures HTTP liveness, not continuous schema/storage readiness;
worker heartbeat monitoring is also pending.

Verified release bundles are described in [application releases](Application_releases.md).
Next: implement host deployment and recovery tooling. Production Auth0,
Tailscale Serve, recovery storage and production import remain later gates.
