# Recovery encryption — 27 October 2026

An encrypted copy of the [verified initial recovery snapshot](Initial_recovery_2026_10_21.md)
has been created on the Mac using age 1.3.2. The snapshot and original backup were
preserved. No production data or private recovery identity was sent to Ubuntu.

| Evidence | Value |
| --- | --- |
| Snapshot | `caf_20261021_133141_258156_7f206242` |
| Ciphertext | `caf_20261021_133141_258156_7f206242.tar.gz.age` |
| Bytes | 855,190,193 |
| Ciphertext SHA-256 | `9ff8f7c7eeb9912331f211333a53d7ac476051e99bad5522f9c6047224d62944` |
| Manifest SHA-256 | `017b9ac533233cf58190916ad29e2c835b0c3e8c54414ef4f665ce7a57f242e1` |
| Authenticated decryption | Passed; all 4,321 archived file hashes matched |

The archive includes the database dump, manifest, 4,317 source/configuration files
and both restore-verification reports. Streaming encryption did not create a
plaintext tar archive. Streaming decryption compared every archived file against
the original and checked the age process exit status, including authentication
of the complete ciphertext. The private output has a checksum sidecar and a
`.verification.json` receipt. The successful database restore from 21 October
is still the database recovery evidence; encryption does not run migrations or
claim a new production cutover snapshot.

## Locations and key custody

- Encrypted copy: `release-output/initial-recovery/encrypted/` on the Mac, outside
  Git inputs. Directory mode is 0700; ciphertext, checksum and receipt are 0600.
- Private identity: `~/.config/caf/recovery/identity.txt` on the Mac, mode 0600 in
  a mode-0700 directory outside the repository. It was not displayed in terminal
  output or chat and must never be copied to Ubuntu or committed.
- Public recipient: `~/.config/caf/recovery/recipient.txt`. Only this file is
  staged on Ubuntu at
  `/home/cafdeploy/caf-staging/production/backup-recipient.txt` for future backup
  encryption. A recipient can encrypt but cannot decrypt.

The owner must save the private identity as a secure attachment or secure note
in the password manager and retain a recovery method independent of this Mac.
This has not been completed or verified by the agent. Losing the identity makes
the encrypted copy unusable. Keeping the key and encrypted file on one Mac does
not protect against losing that Mac; the separate key copy and external backup
location remain acceptance requirements.

## Verify or recover the encrypted copy

These commands run on the Mac, which has age and the project uv environment.
Use an empty, private temporary destination with adequate free space. The archive
is the trusted locally produced artifact identified above; never extract an
untrusted archive without validating its paths first.

```sh
cd /Users/rva/Projects/CA_Study_Guide
cd release-output/initial-recovery/encrypted
shasum -a 256 -c caf_20261021_133141_258156_7f206242.tar.gz.age.sha256
```

Decrypt with `age --decrypt --identity ~/.config/caf/recovery/identity.txt`.
The output is a gzip-compressed tar containing the named snapshot directory.
Require a successful age exit status before accepting decrypted output. Check
the extracted directory with `uv run --no-sync caf-host inspect-backup PATH`,
then run an isolated database restore drill before a recovery or production
import. File inspection alone does not prove a database restore. Keep the
private identity out of shell arguments, environment values and logs; the
`--identity` argument is its filename, not the key contents.

This checkpoint does not configure daily server backups, encryption on Ubuntu,
retention, missing-drive protection or monthly restore automation. Tailscale
Serve remains unconfigured and production services remain stopped. The deployment
PR checks are passing; release acceptance and activation are separate steps.
