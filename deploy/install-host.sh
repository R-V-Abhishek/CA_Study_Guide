#!/bin/bash
# Host-side Docker administration. Packaged Python never receives the Docker socket.
set -euo pipefail
umask 077
bundle=${1:?Usage: caf-host install BUNDLE --backup SNAPSHOT [options]}
shift
snapshot= config=/etc/caf/compose.env root=/srv/caf project=caf port=8788
candidate=()
while (($#)); do
    case $1 in
        --backup) snapshot=${2:?}; shift 2;;
        --env-file) config=${2:?}; shift 2;;
        --root) root=${2:?}; shift 2;;
        --project) project=${2:?}; shift 2;;
        --port) port=${2:?}; shift 2;;
        --allow-candidate) candidate=(--allow-candidate); shift;;
        *) echo 'Unknown install option' >&2; exit 1;;
    esac
done
test -n "$snapshot" || { echo '--backup SNAPSHOT is required' >&2; exit 1; }
command -v jq >/dev/null
command -v flock >/dev/null
bundle=$(realpath -e -- "$bundle")
snapshot=$(realpath -e -- "$snapshot")
config=$(realpath -e -- "$config")
root=$(realpath -e -- "$root")
case "$bundle$snapshot$config$root" in *[,]* ) echo 'Install paths must not contain commas' >&2; exit 1;; esac
test "$root" != / && test -d "$root" && test -w "$root"
case "$snapshot/" in "$root/"*) echo 'Backup must be outside the empty install destination' >&2; exit 1;; esac
test "$(stat -c %a "$config")" = 600 && test "$(stat -c %u "$config")" = "$(id -u)" || {
    echo 'Environment file must be owned by the operator with mode 0600' >&2; exit 1;
}
exec 9> "$root/.deployment.lock"
flock -n 9 || { echo 'Another installation, restore or backup owns the deployment lock' >&2; exit 1; }
test ! -e "$root/installation.json" || { echo 'Installation receipt exists; preserve it and use recovery/update tooling' >&2; exit 1; }
test ! -e "$root/current-compose.json" && test ! -L "$root/current-compose.json" || { echo 'Current deployment pointer exists' >&2; exit 1; }
for name in postgres data backups; do
    test ! -L "$root/$name" || { echo 'Persistent storage must not be a symlink' >&2; exit 1; }
    if test -e "$root/$name"; then
        test -d "$root/$name" && test -r "$root/$name" && test -x "$root/$name" || { echo 'Persistent storage must be an accessible empty directory' >&2; exit 1; }
    fi
    if test -e "$root/$name" && test -n "$(ls -A "$root/$name")"; then
        echo 'Installation requires empty database, document and backup directories' >&2; exit 1
    fi
done
minimum=52428800
if [[ $project == caf-install-* ]] && ((${#candidate[@]})); then minimum=8388608; fi
test "$(df -Pk "$root" | awk 'NR==2 {print $4}')" -ge "$minimum" || { echo 'Insufficient space: production requires 50 GiB; explicit candidates require 8 GiB' >&2; exit 1; }
test -z "$(docker ps -aq --filter "label=com.docker.compose.project=$project")" || { echo 'Compose project already exists' >&2; exit 1; }
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
image_id=$(docker image inspect --format '{{.Id}}' "${CAF_HOST_IMAGE:?Select the verified tooling image}")
mkdir -p "$root/releases"
work=$(mktemp -d "$root/releases/install-XXXXXXXX")
log=$work/install.log
phase=validation started=false success=false
compose() {
    env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$work/compose.json" "$@"
}
finish() {
    code=$?
    trap - EXIT
    if test "$success" != true; then
        if test "$started" = true; then
            compose logs --no-color --tail 50 db web worker >> "$log" 2>&1 || true
            compose stop web worker >> "$log" 2>&1 || true
        fi
        jq -n --arg phase "$phase" --arg project "$project" --arg log "$log" \
            '{status:"failed",phase:$phase,project:$project,private_log:$log,recovery:"Keep serving containers stopped. Preserve database and files; do not rerun install or downgrade the database."}' > "$work/failure.json"
        echo "Installation failed during $phase; services remain stopped. Private record: $work/failure.json" >&2
    fi
    exit "$code"
}
trap finish EXIT
tool() {
    docker run --rm --pull=never --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges:true --pids-limit 64 --memory 512m --cpus 1 \
        --user "$(id -u):$(id -g)" \
        --mount "type=bind,source=$bundle,target=/input/$(basename "$bundle"),readonly" \
        --mount "type=bind,source=$bundle.sha256,target=/input/$(basename "$bundle").sha256,readonly" \
        --mount "type=bind,source=$snapshot,target=/snapshot,readonly" \
        --mount "type=bind,source=$work,target=/output" \
        --entrypoint caf-host "$image_id" "$@"
}
CAF_HOST_IMAGE=$image_id sh "$directory/caf-host" verify-bundle "$bundle" "${candidate[@]}" > "$work/manifest.json" 2>> "$log"
app=$(jq -er .application.reference "$work/manifest.json")
postgres=$(jq -er .postgres.reference "$work/manifest.json")
revision=$(jq -er .commit "$work/manifest.json")
platform=$(jq -er .platform "$work/manifest.json")
tar -xOzf "$bundle" compose.production.yml > "$work/template.yml"
env -i PATH="$PATH" HOME="$HOME" CAF_IMAGE="$app" CAF_POSTGRES_IMAGE="$postgres" \
    CAF_REVISION="$revision" CAF_PLATFORM="$platform" \
    docker compose --env-file "$config" -f "$work/template.yml" --profile tools config --format json \
    > "$work/rendered.json" 2>> "$log"
tool _install prepare "/input/$(basename "$bundle")" /snapshot /output/rendered.json /output \
    --destination "$root" --project "$project" --port "$port" "${candidate[@]}" >> "$log" 2>&1
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
cp "$work/receipt.json" "$root/installation.json"
phase=restore_files
mkdir -p "$root/postgres" "$root/backups" "$root/data"/{blobs,inbox,debug,logs,recovery-configs}
if test -d "$snapshot/blobs"; then cp -a "$snapshot/blobs/." "$root/data/blobs/"; fi
if test -d "$snapshot/configs"; then cp -a "$snapshot/configs/." "$root/data/recovery-configs/"; fi
phase=restore_database started=true
compose run --rm -T --no-deps --user 0:0 --entrypoint sh db -ec \
    'chown postgres:postgres /var/lib/postgresql/data; chmod 700 /var/lib/postgresql/data' >> "$log" 2>&1
compose up -d --wait --wait-timeout 120 db >> "$log" 2>&1
empty=$(compose exec -T db psql -U postgres -d caf -Atc "SELECT count(*) FROM pg_namespace WHERE nspname IN ('app','core','ref','ingest','intel','ops')" 2>> "$log")
test "$empty" = 0 || { echo 'Application database is not empty' >> "$log"; exit 1; }
dump=$(jq -er .dump_file "$work/receipt.json")
compose exec -T db pg_restore -U postgres -d caf --exit-on-error --no-owner --no-acl < "$snapshot/$dump" >> "$log" 2>&1
phase=compare_restored
compose run --rm -T --no-deps --user "$(id -u):$(id -g)" \
    --volume "$snapshot:/snapshot:ro" --entrypoint caf-host admin _install restored /snapshot \
    --expected-manifest-hash "$(jq -er .backup_manifest_sha256 "$work/receipt.json")" >> "$log" 2>&1
phase=permissions
compose run --rm -T --no-deps --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --entrypoint sh admin -ec \
    'chown -R 10001:10001 /srv/caf/data; chown 10001:10001 /srv/caf/data/backups' >> "$log" 2>&1
phase=migrate
compose run --rm -T --no-deps admin db migrate >> "$log" 2>&1
compose run --rm -T --no-deps admin db grants >> "$log" 2>&1
phase=invalidate_copied_credentials
compose exec -T db psql -U postgres -d caf --set ON_ERROR_STOP=1 >> "$log" 2>&1 <<'SQL'
BEGIN;
DELETE FROM app.auth_session;
DELETE FROM app.login_transaction;
UPDATE app.invitation SET revoked_at=now() WHERE consumed_at IS NULL AND revoked_at IS NULL;
COMMIT;
SQL
phase=start
compose up -d --wait --wait-timeout 120 web worker >> "$log" 2>&1
phase=readiness
compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/v1/ready', timeout=5).close()" >> "$log" 2>&1
schema=$(compose exec -T db psql -U postgres -d caf -Atc 'SELECT version_num FROM ops.alembic_version' 2>> "$log")
test "$schema" = "$(jq -er .required_schema "$work/manifest.json")"
jq --arg schema "$schema" --arg work "$work" --arg installed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '.phase="active" | .database_revision=$schema | .release_directory=$work | .installed_at=$installed_at' "$work/receipt.json" > "$root/installation.json.tmp"
mv "$root/installation.json.tmp" "$root/installation.json"
ln -s "$work/compose.json" "$root/current-compose.json"
success=true
echo "Installed verified release; receipt: $root/installation.json"
