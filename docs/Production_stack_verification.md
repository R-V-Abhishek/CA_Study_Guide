# Isolated production stack verification — 18 October 2026

Passed locally on Docker/Colima, using native `linux/arm64`. This is a runtime
integration checkpoint, not acceptance of the Ubuntu `linux/amd64` deployment.
No Ubuntu configuration, production records or existing Docker volumes were changed.

## Image and evidence

- Source: `bcea9dae48f2a6970c3e59ecc46236eaabb12e5c`.
- Local image: `caf:integration-bcea9da-arm64`.
- Image ID: `sha256:42a171f6f133ee3c62da2cd06bacf52641ebb80d3a1f8df7c1f15a0df7000149`.
- Schema: `0009_question_language`.
- Machine-readable [verification receipt](Production_stack_receipt_2026_10_18.json)
  records config hashes, successful steps, image identity and cleanup.

The run uncovered missing versioned runtime configuration in the image. The
Dockerfile now includes `scoring.toml`, `depth.toml`, `sources.toml` and
`models.toml`, and the image verifier checks their presence. The integration test
also compares their SHA-256 hashes against the checked-out files.

## Reproduce

From the repository root with the recorded image loaded:

```sh
uv run --no-sync scripts/verify_production_stack.py \
  --image caf:integration-bcea9da-arm64 \
  --report /tmp/caf-stack-integration.json
sh deploy/verify-image.sh caf:integration-bcea9da-arm64
```

The harness renders `compose.production.yml` using synthetic credentials and an
explicit empty env file. It creates a unique Compose project, substitutes owned
Docker volumes for host paths, and chooses a random host loopback port. Probe
code is sent into containers over stdin. It never loads the application's local
`.env`. Temporary rendered configuration is restricted to mode 0600 and removed
on exit; credentials are excluded from the receipt and redacted from errors.

Successful output ends with `PASS: isolated production stack; receipt: ...`.
Both `passed` and `cleanup_succeeded` must be true in the receipt. A failure exits
nonzero; fix the reported cause and rerun in a fresh disposable project. Cleanup
runs on ordinary failures. If cleanup fails, inspect the exact project recorded
in the receipt and remove only its test resources; preserve other Docker state.

## Verified behavior

- Explicit migrations and grants initialize a new PostgreSQL 16 database.
- All six application roles lack PostgreSQL administrative privileges.
- Web and worker run as UID/GID 10001, with read-only filesystems and dropped
  capabilities. PostgreSQL has no host port; web publishes only on loopback.
- Three synthetic authenticated accounts concurrently read their own private
  notes and update them through the API. Student access to administration is denied.
- Operations and pipeline roles read shared references but cannot read private notes.
- The real worker completes a queued scoring job and reclaims an injected expired lease.
- Notes, progress ownership and document/local-backup file markers survive stopping
  and starting web, worker and database, and recreating web/worker containers.
- Offline image verification passes for Python 3.12, both compiled interfaces,
  runtime config files, migrations, CLI/worker commands, OCR, PostgreSQL 16 clients,
  writable storage and rejection of missing production authentication settings.
- Test containers, volumes and networks were removed. The five pre-existing
  containers remained present after cleanup.

## Remaining gates

Synthetic database sessions bypass Auth0 sign-in. Invalid provider domains and
empty AI keys are used; the probes make no provider requests. Real Auth0 login,
invitations, logout and account disabling remain to be accepted separately.

The production egress network is retained. These tests inspect the published
loopback binding but issue HTTP requests inside the web container. Host HTTP,
Tailscale HTTPS, Ubuntu architecture, host bind permissions, reboot behavior and
measured remote performance remain unverified. An injected expired lease checks
worker recovery logic; it is not a process termination during an active job.

There is no backup/restore, adopted-corpus, migration-failure or rollback drill in
this checkpoint. No `v0.2.0` release bundle or deployment command interface exists
yet. External recovery storage is deferred; production import remains gated on
a verified separately stored recovery backup.
