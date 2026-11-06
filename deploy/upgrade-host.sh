#!/bin/bash
# Host-side Docker administration. Packaged Python never receives the Docker socket.
# Upgrades an ACTIVE installation to a newer verified release. It never downgrades or
# rewrites the database outside forward Alembic migrations, and it always keeps the
# previous release directory, retained bundle and a verified pre-migration snapshot.
set -euo pipefail
umask 077
bundle=${1:?Usage: caf-host upgrade BUNDLE [--env-file FILE] [--root DIRECTORY] [--allow-candidate]}
shift
config=/etc/caf/compose.env root=/srv/caf
candidate=()
while (($#)); do
    case $1 in
        --env-file) config=${2:?}; shift 2;;
        --root) root=${2:?}; shift 2;;
        --allow-candidate) candidate=(--allow-candidate); shift;;
        *) echo 'Unknown upgrade option' >&2; exit 1;;
    esac
done
command -v jq >/dev/null
command -v flock >/dev/null
bundle=$(realpath -e -- "$bundle")
config=$(realpath -e -- "$config")
root=$(realpath -e -- "$root")
case "$bundle$config$root" in *[,]* ) echo 'Upgrade paths must not contain commas' >&2; exit 1;; esac
test "$root" != / && test -d "$root" && test -w "$root" || { echo 'Root must be a writable directory other than /' >&2; exit 1; }
test "$(stat -c %a "$config")" = 600 && test "$(stat -c %u "$config")" = "$(id -u)" || {
    echo 'Environment file must be owned by the operator with mode 0600' >&2; exit 1;
}
exec 9> "$root/.deployment.lock"
flock -n 9 || { echo 'Another installation, upgrade, restore or backup owns the deployment lock' >&2; exit 1; }
receipt=$root/installation.json
test -f "$receipt" && test "$(jq -er .phase "$receipt")" = active || {
    echo 'An active installation receipt is required; use install for a new host' >&2; exit 1;
}
test -L "$root/current-compose.json" || { echo 'Current deployment pointer is missing or not a symlink' >&2; exit 1; }
current=$(realpath -e -- "$root/current-compose.json")
project=$(jq -er .project "$receipt")
test ! -e "$root/.upgrade-in-progress" || { echo 'A previous upgrade did not finish; read its failure.json before continuing' >&2; exit 1; }
for name in postgres data backups; do
    test -d "$root/$name" && test ! -L "$root/$name" || { echo 'Persistent storage must be real directories' >&2; exit 1; }
done
minimum=10485760
if [[ $project == caf-install-* ]] && ((${#candidate[@]})); then minimum=2097152; fi
test "$(df -Pk "$root" | awk 'NR==2 {print $4}')" -ge "$minimum" || { echo 'Insufficient free space for an upgrade, snapshot and retained release' >&2; exit 1; }
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
image_id=$(docker image inspect --format '{{.Id}}' "${CAF_HOST_IMAGE:?Select the verified tooling image for the NEW release}")
mkdir -p "$root/releases"
work=$(mktemp -d "$root/releases/upgrade-XXXXXXXX")
log=$work/upgrade.log
phase=validation stopped=false switched=false migrated=false success=false
old_compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$current" "$@"; }
new_compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$work/compose.json" "$@"; }
point_to() {
    ln -s "$1" "$root/current-compose.json.new"
    mv -T "$root/current-compose.json.new" "$root/current-compose.json"
}
finish() {
    code=$?
    trap - EXIT
    if test "$success" != true; then
        action='Services remain stopped. Preserve the database and files; do not rerun upgrade or downgrade the database.'
        if test "$migrated" = false; then
            # No database change happened, so returning to the previous release is safe.
            if test "$switched" = true; then
                new_compose stop web worker >> "$log" 2>&1 || true
                point_to "$current" >> "$log" 2>&1 || true
            fi
            if test "$stopped" = true; then
                if old_compose up -d --no-deps --wait --wait-timeout 120 web worker >> "$log" 2>&1; then
                    action='The previous release was restarted; the database was not changed.'
                fi
            fi
        elif test "$switched" = true; then
            new_compose stop web worker >> "$log" 2>&1 || true
        fi
        jq -n --arg phase "$phase" --arg project "$project" --arg log "$log" --arg action "$action" \
            --arg previous "$current" --arg snapshot "${created:-}" --argjson migrated "$migrated" \
            '{status:"failed",phase:$phase,project:$project,database_migrated:$migrated,previous_release_compose:$previous,pre_migration_snapshot:(if $snapshot == "" then null else $snapshot end),private_log:$log,recovery:$action}' > "$work/failure.json"
        echo "Upgrade failed during $phase. $action Private record: $work/failure.json" >&2
        # The marker is only removed on success or when the previous release is running again.
        if test "$migrated" = false && test "$action" = 'The previous release was restarted; the database was not changed.'; then
            rm -f "$root/.upgrade-in-progress"
        fi
    else
        rm -f "$root/.upgrade-in-progress"
    fi
    exit "$code"
}
trap finish EXIT
# The backups directory belongs to the application UID, so the host user reads it through the image.
backups() {
    docker run --rm --pull=never --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges:true --pids-limit 64 --memory 128m --cpus 1 --user 10001:10001 \
        --mount "type=bind,source=$root/backups,target=/backups,readonly" \
        --entrypoint "$1" "$image_id" "${@:2}"
}
snapshot_names() {
    local listing
    listing=$(backups ls -1 /backups)
    printf '%s\n' "$listing" | { grep '^caf_' || true; } | sort
}
tool() {
    docker run --rm --pull=never --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges:true --pids-limit 64 --memory 512m --cpus 1 \
        --user "$(id -u):$(id -g)" \
        --mount "type=bind,source=$bundle,target=/input/$(basename "$bundle"),readonly" \
        --mount "type=bind,source=$bundle.sha256,target=/input/$(basename "$bundle").sha256,readonly" \
        --mount "type=bind,source=$work,target=/output" \
        --entrypoint caf-host "$image_id" "$@"
}
CAF_HOST_IMAGE=$image_id sh "$directory/caf-host" verify-bundle "$bundle" "${candidate[@]}" > "$work/manifest.json" 2>> "$log"
app=$(jq -er .application.reference "$work/manifest.json")
postgres=$(jq -er .postgres.reference "$work/manifest.json")
revision=$(jq -er .commit "$work/manifest.json")
platform=$(jq -er .platform "$work/manifest.json")
required=$(jq -er .required_schema "$work/manifest.json")
phase=inspect_installed
running=$(old_compose ps --services --status running | sort | tr '\n' ' ')
[[ " $running" == *" db "* ]] || { echo 'The installed database is not running; start the current release first' >> "$log"; exit 1; }
live=$(old_compose exec -T db psql -U postgres -d caf -Atc 'SELECT version_num FROM ops.alembic_version' 2>> "$log")
port=$(jq -er '.services.web.ports[0].published' "$current")
phase=plan
tar -xOzf "$bundle" compose.production.yml > "$work/template.yml"
env -i PATH="$PATH" HOME="$HOME" CAF_IMAGE="$app" CAF_POSTGRES_IMAGE="$postgres" \
    CAF_REVISION="$revision" CAF_PLATFORM="$platform" \
    docker compose --env-file "$config" -f "$work/template.yml" --profile tools config --format json \
    > "$work/rendered.json" 2>> "$log"
cp "$receipt" "$work/installation.json"
tool _upgrade prepare "/input/$(basename "$bundle")" /output/installation.json /output/rendered.json /output \
    --installed-schema "$live" --port "$port" "${candidate[@]}" >> "$log" 2>&1
phase=image_load
tar -xOzf "$bundle" images.tar | docker image load >> "$log" 2>&1
docker image inspect "$app" "$postgres" > "$work/loaded.json"
tool _install loaded "/input/$(basename "$bundle")" /output/loaded.json >> "$log" 2>&1
retained=$root/releases/$(basename "$bundle")
if test -e "$retained"; then
    cmp -s "$bundle" "$retained" || { echo 'Retained release name already contains different bytes' >> "$log"; exit 1; }
else
    cp "$bundle" "$retained"
    cp "$bundle.sha256" "$retained.sha256"
fi
phase=quiesce
: > "$root/.upgrade-in-progress"
before=$(snapshot_names)
stopped_at=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
stopped=true
old_compose stop web worker >> "$log" 2>&1
phase=snapshot
# pg_dump output is owner-only (the application UID), so inspect it as that UID, read-only.
old_compose run --rm -T --no-deps --entrypoint caf web backup run >> "$log" 2>&1
after=$(snapshot_names)
created=$(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after"))
test "$(printf '%s\n' "$created" | grep -c .)" = 1 || { echo 'Expected exactly one new recovery snapshot' >> "$log"; exit 1; }
snapshot=$root/backups/$created
docker run --rm --pull=never --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --pids-limit 64 --memory 512m --cpus 1 \
    --user 10001:10001 \
    --mount "type=bind,source=$snapshot,target=/snapshot,readonly" \
    --entrypoint caf-host "$image_id" _upgrade verify-snapshot /snapshot \
    --expected-schema "$live" --not-before "$stopped_at" --name "$created" > "$work/snapshot.json" 2>> "$log"
phase=migrate
if test "$live" != "$required"; then
    migrated=true
    new_compose run --rm -T --no-deps admin db migrate >> "$log" 2>&1
    new_compose run --rm -T --no-deps admin db grants >> "$log" 2>&1
fi
phase=activate
point_to "$work/compose.json"
switched=true
new_compose up -d --no-deps --wait --wait-timeout 120 web worker >> "$log" 2>&1
phase=readiness
new_compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/v1/ready', timeout=5).close()" >> "$log" 2>&1
schema=$(new_compose exec -T db psql -U postgres -d caf -Atc 'SELECT version_num FROM ops.alembic_version' 2>> "$log")
test "$schema" = "$required"
expected=$(jq -er --arg ref "$app" '.loaded_images[$ref]' "$work/receipt.json")
running_image=$(docker inspect --format '{{.Image}}' "$(new_compose ps -q web)")
test "$running_image" = "$expected" || { echo 'Running web image differs from the verified release' >> "$log"; exit 1; }
phase=receipt
tool _upgrade finalize /output/installation.json /output/receipt.json /output/snapshot.json /output/installation.merged.json \
    --schema "$schema" --release-directory "$work" >> "$log" 2>&1
cp "$work/installation.merged.json" "$root/installation.json.tmp"
mv "$root/installation.json.tmp" "$root/installation.json"
success=true
echo "Upgraded to $(jq -er .application.version "$root/installation.json"); previous release and snapshot $created are retained."
echo "Receipt: $root/installation.json"
