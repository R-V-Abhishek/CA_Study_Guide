# Private access and cutover preparation — 27 October 2026

Production URL: `https://caf-home.tailf901d2.ts.net/`.

## Verified private HTTPS

The owner enabled Tailscale Serve for the tailnet and applied this command on
Ubuntu with sudo:

```sh
sudo tailscale serve --bg --yes --https=443 http://127.0.0.1:8788
```

`tailscale serve status --json` records HTTPS on port 443 and the loopback proxy.
Listening sockets bind to the laptop's Tailscale addresses. The configuration
has no public Funnel access. From the Mac, HTTPS certificate verification returned
0 and HTTP returned 502, expected while the backend is stopped. This verifies
the private TLS endpoint, not application readiness.

The tailnet has two machines. Its existing policy grants this Mac
(`100.98.186.117`) TCP access to `caf-home` (`100.103.114.54`); it was inspected
without changes. Student devices have not been added or verified. Grant selected
students only application HTTPS access when onboarding them; retain administrator
SSH access separately. Do not replace this policy with default allow-all rules.
The server's current Tailscale node key expires at `2027-04-15T11:00:17Z`.
Reauthenticate before that date or separately approve a server-key expiry policy;
expiry settings were not changed during this setup.

## Auth0 configuration

The existing **CA Study Companion** Regular Web Application was selected by its
client ID from the private production configuration. After explicit owner
approval, these entries were saved and verified by reloading the dashboard:

- Callback: `https://caf-home.tailf901d2.ts.net/auth/callback`.
- Logout return URL: `https://caf-home.tailf901d2.ts.net/`.
- The existing `http://127.0.0.1:8788/auth/callback` remains allowed.

No credentials, grants, CORS settings or other authentication features were
changed. Ubuntu's outbound issuer discovery already passed DNS, TLS, issuer
matching, HTTPS endpoint and PKCE S256 checks. Actual user login/logout still
requires a running application and owner acceptance. Application logout currently
revokes the local application session; configuring the Auth0 logout allowlist
does not add provider-wide logout behavior.

## Application release

[PR #3](https://github.com/R-V-Abhishek/CA_Study_Guide/pull/3) was squash-merged at
`dff36482cfbaf4569cd1843fe4b0c21c7246b9bc`. The refreshed release PR changed only
the root application version, matching lock entry, release manifest and changelog.
[Its exact-branch CI](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/40441103290)
passed application checks and the native amd64 bundle/installation drill at
`a59c6771ae122b0e0ab3a604b2f308b5418e1e5f`.

[PR #2](https://github.com/R-V-Abhishek/CA_Study_Guide/pull/2) was then accepted.
Tag `v0.2.0` identifies `2821dfc0b20cad99e723b03bf8ae5e2b63747d23`.
[Tagged publication](https://github.com/R-V-Abhishek/CA_Study_Guide/actions/runs/40442380429)
passed and published the non-candidate production bundle. Its checksums,
architecture, commit and both dependency-lock hashes matched on the Mac; lock
hashes were independently checked against Git tag `v0.2.0`.
Ubuntu's `/opt/caf/repo` was cloned from the integrated main branch and then
fast-forwarded to this accepted release commit. Git updates did not start services.

## Fresh recovery snapshot

The selected snapshot is `caf_20261027_025947_379520_b1ac35d7`, schema
`0009_question_language`, preserving the active `baseline-2026-10-16` adoption.
The adopted content/taxonomy manifest hash remains
`c59e12cb4f9696adbcc4647b0775542693517aa23870e37edfca753497370973`, taxonomy
version 9, bound to attempt `2027-05`. This content identity is independent of
application release `v0.2.0` and the recovery manifest hash below.
The existing administrator account is active and identity-bound. A fresh isolated
restore matched all 76 table digests, the migration schema and 4,317 archived
source/configuration files. A final read-only comparison found that the live Mac
source still matched the snapshot. There was no local web listener or intelligence
worker at the process check before cutover preparation.

| Identity | SHA-256 |
| --- | --- |
| Snapshot manifest | `a0066e0c943fc43402b9f7933a2f4ec47393cefb0e67d885d5705d920d3fdacd` |
| Encrypted archive | `b7f41731aab516b9a30c21790bb287065ba707c2078ad0d84b5822a05c54eb65` |

The new encrypted Mac copy is 855,189,830 bytes. Authenticated decryption matched
all 4,320 archived files, including the dump, manifest and successful verification
report. The original snapshot/encrypted copy was preserved. Key custody is
recorded in [recovery encryption](Recovery_encryption.md).

The snapshot was decrypted on the Mac and streamed through SSH to private Ubuntu
staging at `/home/cafdeploy/caf-staging/production/recovery/` without transferring
the private key. Packaged `inspect-backup` then verified its full file inventory
and hashes on Ubuntu. That command reports `restore_verified: false` deliberately;
the successful isolated database restore is separate evidence, retained on the Mac.
Production import must target empty storage and recheck every restored table/file.

Colima was stopped at the first fresh-drill attempt. Its existing VM was started
with the saved configuration, then the isolated drill passed through a temporary
loopback SSH tunnel. The live source is native Homebrew PostgreSQL with a separate
data directory. Temporary drill resources were removed; live source data and
existing Docker state were preserved.
