# Ubuntu candidate staging, 20 October 2026

The candidate from [passing CI run 39296744618](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/39296744618)
was downloaded to the Mac, fully verified, transferred over Tailscale SSH, and
checked again on Ubuntu. This is a tooling checkpoint, not a production release.
The v0.2.0 release PR remains pending.

## Source and identities

The artifact is `caf-v0.1.0-candidate-40cec057991f-linux-amd64.tar.gz`.
Source commit `40cec057991fbb51cf4cc27bccdf388af8c159b7` is GitHub's synthetic
PR merge commit. Its tree `543320c0c21205ff1c3a2a98602ff49bcf9d687d` exactly
matches reviewed branch revision `f4b07090f4cffbafec77ce3c3e177e7bd67995e7`.

| Image | Recorded configuration digest | Ubuntu OCI manifest digest |
| --- | --- | --- |
| Application | `sha256:c87166dfabb2edb481a9acf95942f061897cf82b3a408c4dd7bdd1efcf1a1c20` | `sha256:9bc95bf372f024dbd7240556cc2e600e71831a1c59a60dda042c5311bb8d13a5` |
| PostgreSQL | `sha256:e8538db784b854a9baac5c1be6d059dcf0db257af2d94c8c5807b5fc15f11222` | `sha256:37fe3baeb05c2c980e5d15e247b061274c81b0db335241d023dbf7f840463f44` |

The initial strict image-ID comparison stopped after loading the images because
Ubuntu's containerd store reports manifest digests, while the CI builder recorded
configuration digests. Both identities were reconciled against the actual
checksummed Docker archive, including each manifest's hash and referenced config
hash. Loaded architectures and application revision/version labels also matched.
The load verifier now accepts either identity only when linked by that archive.
It still rejects unrelated images. See [Docker's containerd store documentation](https://docs.docker.com/engine/storage/containerd/).
No Docker daemon configuration was changed.

## Tested commands and results

On the Mac:

```sh
uv run --no-sync caf-host verify-bundle \
  release-output/ci-39296744618/caf-v0.1.0-candidate-40cec057991f-linux-amd64.tar.gz \
  --platform linux/amd64 --allow-candidate
uv run --no-sync pytest -q deploy/tests
```

All bundle hashes and metadata passed; 23 deployment tests passed, including
classic/containerd identity mappings, corrupt metadata and wrong-image rejection.
The corrected identity helper was also exercised against the actual downloaded
archive and actual Ubuntu `docker image inspect` results. Full CI for this code
change is separate from the earlier passing artifact build linked above.

Private staging directory on Ubuntu:
`/home/cafdeploy/caf-staging/f4b07090f4cf`. It contains the archive, checksum,
verified manifest, two host launcher scripts and resulting reports. This is a
temporary test location; `/opt/caf/repo`, `/etc/caf` and `/srv/caf` remain absent.

From that directory on Ubuntu:

```sh
export CAF_HOST_IMAGE=sha256:9bc95bf372f024dbd7240556cc2e600e71831a1c59a60dda042c5311bb8d13a5
sh tools/caf-host preflight > preflight-2026-10-20.json
# Expected exit 2: report produced with two warnings.
sh tools/caf-host verify-bundle \
  caf-v0.1.0-candidate-40cec057991f-linux-amd64.tar.gz --allow-candidate \
  > host-verified-manifest.json
# Expected exit 0.
```

The real Ubuntu launcher passed both operations. Preflight found no automated
blockers, with warnings for the deferred backup drive and the unprivileged
firewall read. Free space was 411,886,407,680 bytes. Manual readiness gates listed
in [host preflight](Host_preflight.md) remain pending.

The report SHA-256 is
`5daa777f9a203372f4fd2d9476680ee8c42e2bf47eb2faa7754eb91f8c82bc28`.
A matching private Mac copy is under `release-output/ci-39296744618/`.
The image identity receipt is `ubuntu-image-identities.json` in that Mac directory.

`deploy/verify-image.sh` also passed on Ubuntu: non-root Python 3.12, both compiled
interfaces, migrations, CLI/worker, OCR, PostgreSQL 16 client, writable temporary
storage and rejection of missing production Auth0 configuration. No application
or database service was started. All temporary containers were removed, and
`docker ps -a` was empty afterward. The two candidate images remain loaded.
