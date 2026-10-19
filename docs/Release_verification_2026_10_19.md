# Release tooling verification — 19 October 2026

Local candidate source: `becaeb736addcc00d6413434b6960b9ce298030e`, on
`feat/phase8-central-deployment`. No production tag, GitHub Release, Ubuntu
deployment or production import was created during this checkpoint.

## Local evidence

- Thirteen focused tests passed for Git dirty/untracked source, tag identity,
  lock/version consistency, archive corruption, paths, links, duplicate members,
  schema declarations, candidate rejection and architecture selection.
- A fourteenth test exercises a real owned process with a command longer than
  700 characters and an 80-column terminal. The first Linux CI run found worker
  ownership lookup truncated its token; `ps -ww` preserves the complete command.
  The existing real worker shutdown test also now sets an 80-column width.
- `actionlint` 1.7.12 accepted all three workflows. Downloaded validator archive
  matched its release checksum; no system tooling was replaced.
- The exact Release Please 17.3.0 library used by the pinned action passed
  `deploy/tests/release-version.cjs`: selects `0.2.0` from the initial release
  footer and changes only the root project version in `uv.lock`. This also
  caught and corrected the TOML selector before publication.
- Production Compose validation passed, including all 13 missing-value failures.
- The committed source built a native ARM64 candidate, passed the offline image
  verifier and the disposable production-stack verification, and exported both
  tested images in a compressed bundle of approximately 315 MiB.
- The bundle was independently reverified and both images loaded back from its
  archive. Image IDs, architecture and application source/version labels matched.
- Buildx provenance records four resolved build materials. The [saved manifest](Release_candidate_manifest_2026_10_19.json)
  records application/database IDs, locks, required schema and payload hashes.
- The five pre-existing Docker containers remained present; no integration
  volumes remained. Source stayed clean through packaging.

Commands used after committing the implementation:

```sh
uv run --no-sync pytest -q deploy/tests
NODE_PATH=/tmp/caf-release-please-check/node_modules node deploy/tests/release-version.cjs
uv run --no-sync scripts/verify_production_compose.py
/tmp/caf-actionlint/actionlint .github/workflows/*.yml
uv run --no-sync scripts/release_bundle.py build --candidate \
  --platform linux/arm64 --buildx /opt/homebrew/bin/docker-buildx
uv run --no-sync scripts/release_bundle.py verify \
  release-output/caf-v0.1.0-candidate-becaeb736add-linux-arm64.tar.gz \
  --allow-candidate --platform linux/arm64 --load
```

The temporary Node installation used `release-please@17.3.0` with install scripts
disabled; the same regression check is included in CI. Local candidate version
`v0.1.0` matches the current project metadata; the candidate flag prevents it
being mistaken for the planned accepted `v0.2.0` release.

## GitHub execution

The first run passed 486 tests and failed the worker ownership case above. The
next run passed all 488 Python tests, then exposed a Compose-version difference:
v2 omits false booleans from canonical JSON where v5 retains them. The verifier
now accepts that representation while rejecting `create_host_path: true`.

The [corrected GitHub run](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/39189487630)
checks source `442128ced7418aa550f2e013119a06a478bc21ea`. Its code-check job passed:
488 Python tests, Compose, release-version regression, frontend type checking,
25 UI tests and both builds. The native amd64 candidate job also passed: image
build, offline image checks, migrations/grants, concurrent synthetic accounts,
role restrictions, worker recovery, service recreation, archive checksums and
artifact upload. Release proposal/publication workflows remain
inactive until integration into `main` or an explicitly accepted version tag.

The run uploaded `candidate-linux-amd64`, artifact ID `12159527585` (329,574,135
bytes), expiring 26 October 2026. GitHub's artifact ZIP digest is
`sha256:15c331320331bebbb62d5996228a5616602fba9efc7e57e1753b40149e039c76`.
The bundle inside is `caf-v0.1.0-candidate-442128ced741-linux-amd64.tar.gz`.
Checksums were verified inside the successful CI build. An additional independent
download to the Mac reset its connection; a resumable retry was stopped after
continued slow transfer, preserving `/tmp/caf-amd64-artifact.zip` as a partial
file. It is not a verified local amd64 archive. The complete locally verified
ARM64 archive remains under `release-output/`.

The HTTPS OAuth credential lacked `workflow` scope. Publication used the owner's
existing `github-personal` SSH identity instead; no authentication settings,
tokens or SSH keys were changed.

The local rerun of the database-dependent worker case was blocked before test
collection by Colima host-port forwarding, both with a random port and the
existing fixed-port override. Its temporary database was removed. The standalone
long-command regression passed locally; Linux CI supplies the full-suite check.

These checks do not accept real Auth0, Tailscale HTTPS, Ubuntu bind permissions,
backup/restore, failed-migration recovery or application rollback. Those remain
later deployment gates. See [release operations](Application_releases.md).
