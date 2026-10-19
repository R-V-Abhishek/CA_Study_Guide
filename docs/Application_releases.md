# Application releases and GitHub Actions

Application bundles can be built on the Mac or by GitHub Actions using the same
repository-owned Typer command. GitHub Releases stores the resulting archives;
there is no required image registry. Publishing a release does not deploy Ubuntu.

## Commit messages and acceptance

On `main`, Release Please proposes a release PR from Conventional Commits:

| Commit | Version effect |
| --- | --- |
| `fix: repair note saving` | Patch |
| `feat: add a study feature` | Minor |
| `feat!: change an incompatible contract` or a `BREAKING CHANGE:` footer | Major after 1.0; minor before 1.0 |
| `docs:`, `test:`, `chore:`, `ci:` | No application release by themselves |

The first home release is planned as `v0.2.0`. Release Please updates the root
`pyproject.toml`, the matching `ca-final` entry in `uv.lock`, its version manifest,
and `CHANGELOG.md`. Internal workspace package and frontend package versions are
independent; the image's application version is the root project version.
Use a Conventional Commit title when squash-merging an application PR.
The initial automation checkpoint includes a `Release-As: 0.2.0` footer to select
the first version explicitly. Preserve that footer if squashing this work into
`main`; later release cycles use the ordinary commit-based version calculation.

Review and merge the release PR to accept its version. The automation creates a
tag and draft release, then calls the bundle workflow directly. This avoids the
default `GITHUB_TOKEN` restriction on triggering workflows from bot-created tags.
After tests, image checks, synthetic stack checks and packaging succeed, it
uploads the bundle and SHA-256 sidecar and publishes the draft. Failed builds
leave the draft unpublished. No Ubuntu credentials or paid model keys are used.

GitHub does not automatically start CI on PRs created with its default bot token.
For a release PR, manually dispatch **Application checks** on that PR's branch
before merging. The publishing workflow independently reruns the Python tests,
frontend type/UI checks, production configuration checks, image build and runtime
verification against the accepted tag. A GitHub App token can be added later if
automatic checks on bot PRs become necessary; no personal access token is needed
for the current workflow.

Workflow definitions are effective after reaching `main`. The current work stays
on `feat/phase8-central-deployment` until reviewed; no release is created merely
by pushing that branch.

## Workflows

- **Application checks**: Python tests, frontend type/UI/build checks and Compose
  validation, followed by an Ubuntu amd64 candidate build and disposable stack
  verification. Candidate artifacts expire after seven days.
- **Propose application release**: release PR/version/changelog automation on
  `main`, followed by the reusable publishing workflow when a release is accepted.
- **Publish verified release bundle**: accepted `v*` tags or a manual dispatch
  naming an existing tag. Requires the tag to be on `main` and match the root
  project version. Can resume publication after a corrected environmental failure.

Workflow actions are pinned to commit hashes. Read-only CI has no release write
permissions; publishing has repository contents write permission. There is no
deployment runner on the home laptop, SSH action, or automatic production update.

## Bundle contents and identities

Each `.tar.gz` contains only:

- `images.tar`: the exact application and tested PostgreSQL 16 images.
- `manifest.json`: version, candidate flag, exact Git commit, image IDs, platform,
  UTC build time, dependency-lock hashes, schema requirements and file hashes.
- `SHA256SUMS`: SHA-256 for every payload and the manifest.
- Versioned Compose configuration, environment template and offline image verifier.
- Release notes, Buildx metadata/provenance and synthetic stack verification receipt.

The outer `.tar.gz.sha256` verifies the whole compressed artifact. Both images
are given local references recorded in the manifest. Set `CAF_IMAGE`,
`CAF_POSTGRES_IMAGE`, `CAF_REVISION` and `CAF_PLATFORM` from that manifest when
deployment tooling is ready. Loading a bundle starts no service.

Hashes detect corruption; they do not establish who produced a bundle. Obtain
the archive and sidecar from the accepted repository release or the owner's
verified transfer. Never publish database dumps, source documents, `.env`, Auth0
credentials or recovery material as GitHub release assets. Content and recovery
snapshots remain separate from application releases.

`deploy/compatibility.toml` currently supports only `0009_question_language`.
Packaging fails if that required revision differs from the migration head.
Additional schema compatibility is refused until there is a tested rollback
drill. A schema declaration is not evidence that restoring an old database is
safe; database restoration remains a separate recovery operation.

## Local commands

Review and commit all implementation changes first. The builder rejects tracked
modifications and untracked files, requires matching project/lock versions, and
builds from `git archive` so ignored local files cannot enter the build context.

For a Mac ARM64 candidate before a production tag exists:

```sh
uv run --no-sync scripts/release_bundle.py build --candidate \
  --platform linux/arm64 --buildx /opt/homebrew/bin/docker-buildx
```

Candidates include their commit in the filename and cannot pass production
selection without `--allow-candidate`. They do not claim to be `v0.2.0` releases.
To verify and load a candidate, substitute its actual archive path:

```sh
uv run --no-sync scripts/release_bundle.py verify \
  release-output/<candidate>.tar.gz --allow-candidate --platform linux/arm64 --load
```

For an accepted release checkout with its matching tag:

```sh
uv run --no-sync scripts/release_bundle.py build --platform linux/amd64
uv run --no-sync scripts/release_bundle.py verify \
  release-output/caf-v0.2.0-linux-amd64.tar.gz --platform linux/amd64 --load
```

Use the standalone Homebrew Buildx path on the Mac when Docker does not discover
the plugin. Ubuntu GitHub runners use `docker buildx`. Runtime verification must
support the target architecture; native amd64 CI is preferred to emulation on
the Mac. Persistent paths in tests are disposable volumes, not production binds.

The output directory is ignored by Git. Existing bundles are never overwritten.
Verification streams and hashes members without extracting paths, rejects extra
files, duplicates and links, and checks the chosen architecture before loading.
Loading also checks both image IDs and application version/source labels. It
does not migrate a database, activate a release, or touch application storage.

## Failures and retention

On dirty source or mismatched tag/lock/schema, fix and commit the source before
retrying. Do not weaken the guard. On stack failure, inspect its error and owned
test project; ordinary failure paths clean up their disposable containers and
volumes. An interrupted process may leave that uniquely named project for manual
inspection. Preserve unrelated Docker resources.

If publication fails, inspect the Actions run and draft release. Existing assets
are not overwritten (`--clobber` is deliberately absent). Do not rebuild or
replace a published version silently; fix source through a new release. Never
delete a retained image required by a recovery snapshot.

Retain the current and two previous application bundles locally, and any older
checksummed artifact required by retained backups. GitHub's short-lived candidate
artifacts are not the production archive. Transfer accepted bundles privately to
Ubuntu later; branch updates alone must never change the running application.

Host installation, deployment locking, maintenance/readiness gates, encrypted
recovery and rollback commands remain subsequent implementation steps. These
workflows do not replace the Ubuntu and real Auth0 acceptance checks.
