#!/bin/bash
# Host-side content administration. Packaged Python never receives the Docker socket.
# A content snapshot adds source documents to the ACTIVE installation in one transaction after a
# fresh recovery snapshot. Extraction and classification batches then run in one-off containers of
# the installed image; confirming, reviewing and publishing stay administrator actions in the UI.
set -euo pipefail
umask 077
usage='Usage: caf-host content import BUNDLE
       caf-host content extract (--doc ID | --limit N)
       caf-host content classify-export --taxonomy RELEASE --revision ID [--revision ID ...] [--name NAME]
       caf-host content classify-import BATCH RESULTS_DIRECTORY
Every form accepts --root DIRECTORY.'
fail_usage() { echo "$usage" >&2; exit 1; }
action=${1:-}
test -n "$action" || fail_usage
shift
root=/srv/caf batch_name='' positional=() options=()
while (($#)); do
    case $1 in
        --root) root=${2:?}; shift 2;;
        --doc|--limit|--revision)
            [[ ${2:-} =~ ^[1-9][0-9]{0,8}$ ]] || { echo "$1 needs a positive whole number" >&2; exit 1; }
            options+=("$1" "$2"); shift 2;;
        --taxonomy)
            [[ ${2:-} =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || { echo 'Invalid taxonomy release' >&2; exit 1; }
            options+=("$1" "$2"); shift 2;;
        --name)
            [[ ${2:-} =~ ^[a-z0-9][a-z0-9._-]{0,63}$ ]] || { echo 'Invalid batch name' >&2; exit 1; }
            batch_name=$2; shift 2;;
        --*) echo "Unknown content option: $1" >&2; exit 1;;
        *) positional+=("$1"); shift;;
    esac
done
has() { [[ " ${options[*]-} " == *" $1 "* ]]; }
case $action in
    import) test "${#positional[@]}" = 1 && test "${#options[@]}" = 0 || fail_usage;;
    extract)
        test "${#positional[@]}" = 0 && (has --doc || has --limit) && ! has --taxonomy && ! has --revision || fail_usage;;
    classify-export)
        test "${#positional[@]}" = 0 && has --taxonomy && has --revision && ! has --doc && ! has --limit || fail_usage;;
    classify-import) test "${#positional[@]}" = 2 && test "${#options[@]}" = 0 || fail_usage;;
    *) fail_usage;;
esac
test "$action" = classify-export || test -z "$batch_name" || fail_usage
command -v jq >/dev/null && command -v flock >/dev/null || { echo 'jq and flock are required' >&2; exit 1; }
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$directory/lib.sh"
root=$(realpath -e -- "$root")
case $root in *[,:]* ) echo 'Root must not contain commas or colons' >&2; exit 1;; esac
active_installation "$root"
jq -e '.services.content' "$current" > /dev/null || { echo 'The installed release has no content service; upgrade first' >&2; exit 1; }
mkdir -p "$root/content"
chmod 700 "$root/content"
# Upgrades refuse to start while this lock is held, so content never runs across a release change.
exec 8> "$root/.content.lock"
flock -n 8 || { echo 'Another content import, extraction or batch is running' >&2; exit 1; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)

# A directory the application UID can read through a read-only bind mount.
staging() {
    work=$(mktemp -d "$root/content/$1-XXXXXXXX")
    chmod 755 "$work"
}

import_snapshot() {
    local bundle name started status snapshot id
    # The EXIT trap reads these, so they are global.
    phase=verify imported=false
    bundle=$(realpath -e -- "${positional[0]}")
    name=$(basename "$bundle")
    [[ $name =~ ^content-[0-9a-f]{12}\.tar\.gz$ ]] || { echo 'Expected a content-<id>.tar.gz bundle' >&2; exit 1; }
    test -f "$bundle.sha256" || { echo "Missing checksum file $bundle.sha256" >&2; exit 1; }
    test "$(df -Pk "$root" | awk 'NR==2 {print $4}')" -ge 5242880 || { echo 'Insufficient free space for a recovery snapshot and import' >&2; exit 1; }
    staging import
    log=$work/import.log
    install -m 0644 "$bundle" "$bundle.sha256" "$work/"
    trap 'code=$?; if test "$code" != 0; then
            jq -n --arg phase "$phase" --arg log "$log" --argjson imported "$imported" \
                "{status:\"failed\",phase:\$phase,documents_added:\$imported,private_log:\$log}" > "$work/failure.json"
            if $imported; then echo "Content was imported, but recording it failed during $phase. Record: $work/failure.json" >&2
            else echo "Content import failed during $phase; no documents were added. Record: $work/failure.json" >&2; fi
        fi' EXIT
    # caf creates its storage directories on start; give it a private, empty one.
    docker run "${sandbox[@]}" --memory 512m --user 10001:10001 \
        --tmpfs /srv/caf/data:rw,noexec,nosuid,size=16m,uid=10001,gid=10001 \
        --mount "type=bind,source=$work,target=/input,readonly" \
        --entrypoint caf "$image" content verify "/input/$name" > "$work/verify.json" 2>> "$log"
    phase=snapshot
    started=$(date -u +%Y-%m-%dT%H:%M:%S)
    bash "$directory/backup-host.sh" --root "$root" >> "$log" 2>&1
    status=$(docker run "${sandbox[@]}" --memory 128m --user 10001:10001 \
        --mount "type=bind,source=$root/backups,target=/backups,readonly" \
        --entrypoint cat "$image" /backups/status.json)
    snapshot=$(jq -er --arg started "$started" 'select(.state == "ok" and .last_success_at >= $started) | .snapshot.name' <<< "$status")
    phase=import
    exec 9> "$root/.deployment.lock"
    flock -w 600 9 || { echo 'The deployment lock stayed busy for 10 minutes' >> "$log"; exit 1; }
    compose run --rm -T --no-deps --volume "$work:/input:ro" content content import "/input/$name" > "$work/import.out" 2>> "$log"
    imported=true
    phase=receipt
    tail -n 1 "$work/import.out" > "$work/import.json"
    id=$(jq -er .snapshot_id "$work/import.json")
    jq -n --slurpfile result "$work/import.json" --arg bundle "$name" --arg sha "$(cut -d' ' -f1 "$bundle.sha256")" \
        --arg snapshot "$snapshot" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg work "$work" \
        '$result[0] as $r | {format_version:1,status:"imported",snapshot_id:$r.snapshot_id,bundle:$bundle,bundle_sha256:$sha,run_id:$r.run_id,imported:$r.imported,existing:$r.existing,created_attempts:$r.created_attempts,recovery_snapshot:$snapshot,imported_at:$at,private_directory:$work}' \
        > "$work/receipt.json"
    mkdir -p "$root/content/receipts"
    cp "$work/receipt.json" "$root/content/receipts/$id-$stamp.json"
    # Nightly retention keeps the snapshot named here until a later import replaces it.
    cp "$work/receipt.json" "$root/content/last-import.json.new"
    mv -T "$root/content/last-import.json.new" "$root/content/last-import.json"
    jq '{snapshot_id,imported:(.imported|length),existing:(.existing|length),created_attempts,recovery_snapshot,receipt:"content/receipts/\(.snapshot_id)-'"$stamp"'.json"}' "$work/receipt.json"
}

extract() {
    local log=$root/content/extract-$stamp.log
    # Only confirmed documents with verified provenance are selected; nothing is promoted here.
    compose run --rm -T --no-deps content extract run --ocr "${options[@]}" 2>&1 | tee "$log"
}

classify_export() {
    local name=${batch_name:-batch-$stamp} out
    mkdir -p "$root/content/outbox"
    out=$root/content/outbox/$name.json
    test ! -e "$out" || { echo "Batch already exists: $out" >&2; exit 1; }
    # The manifest is written inside the container's private /tmp, then streamed out.
    compose run --rm -T --no-deps --entrypoint sh content \
        -c 'caf classify export --output /tmp/batch.json "$@" >&2 && cat /tmp/batch.json' sh "${options[@]}" \
        > "$out.partial"
    jq -e '.batch_key and (.records | length > 0)' "$out.partial" > /dev/null
    mv "$out.partial" "$out"
    echo "Exported $(jq '.records | length' "$out") questions to $out (batch $(jq -r .batch_key "$out"))"
}

classify_import() {
    local batch results file
    batch=$(realpath -e -- "${positional[0]}")
    results=$(realpath -e -- "${positional[1]}")
    test -d "$results" || { echo 'RESULTS_DIRECTORY must be a directory' >&2; exit 1; }
    staging classify-import
    install -m 0644 "$batch" "$work/batch.json"
    mkdir -m 755 "$work/results"
    for file in "$results"/*.json; do
        test -e "$file" || continue
        install -m 0644 "$file" "$work/results/"
    done
    compose run --rm -T --no-deps --volume "$work:/input:ro" content \
        classify import --batch /input/batch.json --output-dir /input/results 2>&1 | tee "$work/import.log"
}

case $action in
    import) import_snapshot;;
    extract) extract;;
    classify-export) classify_export;;
    classify-import) classify_import;;
esac
