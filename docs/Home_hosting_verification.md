# Container packaging verification — 2026-10-18

This is a packaging checkpoint, not production deployment acceptance.

- Source: `6cf0ccf`, exported with `git archive HEAD` into an isolated temporary
  directory, without the Mac's uncommitted application changes or `.git`.
- Builder: Mac Colima, ARM64, 2 CPUs, approximately 2 GB VM RAM; Buildx 0.38.0.
- Target: `linux/amd64`, matching the Ubuntu laptop.
- Image: `caf:committed-packaging-check`.
- Local image identity:
  `sha256:97f83488c60726ad16c40b672aba7c3fee9252dc4e7000c95f34f6132c6672fd`.
- Image user: `10001:10001`.
- Both interfaces passed their TypeScript and Vite production builds.
- Python dependencies installed using Python 3.12, uv 0.11.19, and the frozen lock.

The working-tree image also built successfully. The committed-source build is
the evidence that this packaging checkpoint does not rely on uncommitted files.
It does not include newer baseline, reader, review, or other application edits
still pending their own reviewed Git checkpoint.

## Verification procedure

```sh
sh deploy/verify-image.sh caf:committed-packaging-check
```

The smoke test uses no networking, credentials, database, host mounts, or exposed
ports. Its optional OpenRouter credential check uses the environment because the
older committed application does not yet declare that provider's settings field.

Result: **PASS**, exit code 0. Verified non-root Python 3.12 execution, both compiled
interfaces, application imports, writable data storage, production authentication
guard, `caf --help`, `caf intel worker --help`, `alembic heads`, Tesseract, and
PostgreSQL 16 `pg_dump`. No local `.env`, Git checkout, data directory, Node
dependencies, or AI credentials were bundled. Shell and Node syntax checks and
Git whitespace checks also passed.

## Build findings

- Running pnpm 12.6.0 under x86 emulation failed in its Rust I/O runtime. Building
  static frontend assets on the builder's native architecture resolved this.
- Debian Bookworm's default PostgreSQL client is version 15. The Dockerfile uses
  PostgreSQL's signed package repository to install client version 16 explicitly.
- One overlapping build/test run exited 137 in the small local VM. Verification
  is run after the build completes; existing database/browser containers are left
  running.
- Authlib and PyMuPDF emit deprecation warnings during imports.

## Not yet verified

Auth0 login, database migrations and grants, web/worker startup against PostgreSQL,
production Compose, private HTTPS, backup/restore, or student activity. No image
was transferred to Ubuntu, and no production data was imported.
