#!/bin/bash
# Daily recovery snapshot. Host-side Docker administration; packaged Python never receives the Docker socket.
# The snapshot, its file-integrity check and retention run in a one-off container of the installed web image.
# Optional encryption to a PUBLIC recipient happens here with the host's `age`; the private identity never
# belongs on this machine. A snapshot's database restore has not been proven by this script (see docs).
set -euo pipefail
umask 077
root=/srv/caf recipient=/etc/caf/backup-recipient.txt
while (($#)); do
    case $1 in
        --root) root=${2:?}; shift 2;;
        --recipient) recipient=${2:?}; shift 2;;
        *) echo 'Unknown backup option' >&2; exit 1;;
    esac
done
command -v jq >/dev/null
command -v flock >/dev/null
root=$(realpath -e -- "$root")
case "$root$recipient" in *[,]* ) echo 'Backup paths must not contain commas' >&2; exit 1;; esac
exec 9> "$root/.deployment.lock"
flock -n 9 || { echo 'Another installation, upgrade, restore or backup owns the deployment lock' >&2; exit 1; }
receipt=$root/installation.json
test -f "$receipt" && test "$(jq -er .phase "$receipt")" = active || { echo 'An active installation is required' >&2; exit 1; }
# A failed upgrade's pre-migration snapshot is not yet named in the receipt, so retention could prune it.
test ! -e "$root/.upgrade-in-progress" || { echo 'A previous upgrade did not finish; read its failure.json before taking or pruning snapshots' >&2; exit 1; }
test -L "$root/current-compose.json" || { echo 'Current deployment pointer is missing' >&2; exit 1; }
current=$(realpath -e -- "$root/current-compose.json")
project=$(jq -er .project "$receipt")
compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$current" "$@"; }
image=$(jq -er .services.web.image "$current")
# The backups directory belongs to the application UID, so the host user reads it through the image.
backups() {
    docker run --rm --pull=never --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges:true --pids-limit 64 --memory 128m --cpus 1 --user 10001:10001 \
        --mount "type=bind,source=$root/backups,target=/backups,readonly" \
        --entrypoint "$1" "$image" "${@:2}"
}
minimum=5242880
test "$(df -Pk "$root" | awk 'NR==2 {print $4}')" -ge "$minimum" || { echo 'Insufficient free space for a recovery snapshot' >&2; exit 1; }
# Snapshots that upgrade receipts name as rollback points are never pruned by retention.
protect=()
while read -r kept; do protect+=(--protect "$kept"); done < <(jq -r '.previous[]?.snapshot.name | strings' "$receipt")
compose run --rm -T --no-deps --entrypoint caf-host web _backup run "${protect[@]}"
status=$(backups cat /backups/status.json)
name=$(jq -er .snapshot.name <<< "$status")
case $name in caf_[0-9]*_[0-9]*_[0-9]*_[0-9a-f]*) ;; *) echo 'Unexpected snapshot name' >&2; exit 1;; esac
mark() { compose run --rm -T --no-deps --entrypoint caf-host web _backup mark-encryption "$1" > /dev/null; }
if test ! -e "$recipient"; then
    mark not_configured
    echo "Snapshot $name verified for file integrity. Encryption is not configured (no $recipient)."
    exit 0
fi
command -v age >/dev/null || { mark 'failed:age_not_installed'; echo 'age is required because a backup recipient is configured' >&2; exit 1; }
encrypted=$root/encrypted-backups
mkdir -p "$encrypted"
chmod 700 "$encrypted"
if ! docker run --rm --pull=never --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges:true --pids-limit 64 --memory 256m --cpus 1 --user 10001:10001 \
        --mount "type=bind,source=$root/backups/$name,target=/snapshots/$name,readonly" \
        --entrypoint tar "$image" -czf - -C /snapshots "$name" | age --recipients-file "$recipient" -o "$encrypted/$name.tar.gz.age.partial"; then
    rm -f "$encrypted/$name.tar.gz.age.partial"
    mark 'failed:encryption_error'
    echo 'Encryption failed; the unencrypted snapshot is retained' >&2
    exit 1
fi
test -s "$encrypted/$name.tar.gz.age.partial"
mv "$encrypted/$name.tar.gz.age.partial" "$encrypted/$name.tar.gz.age"
(cd "$encrypted" && sha256sum "$name.tar.gz.age" > "$name.tar.gz.age.sha256")
mark encrypted
# Keep encrypted copies only for snapshots that retention kept.
for file in "$encrypted"/caf_*.tar.gz.age; do
    test -e "$file" || continue
    id=$(basename "$file" .tar.gz.age)
    if ! jq -e --arg id "$id" '.retained | index($id)' <<< "$status" > /dev/null; then
        rm -f -- "$file" "$file.sha256"
    fi
done
echo "Snapshot $name verified for file integrity and encrypted to $encrypted/$name.tar.gz.age"
