#!/bin/bash
# Push alerts. Runs every few minutes; sends one notification per problem, one when it clears and a daily
# reminder. Nothing is sent unless CAF_WATCH_WEBHOOK_URL is set (for example an ntfy topic) in /etc/caf/watch.env.
# Evaluation and de-duplication state live in the web image (backups/watch-state.json); this script only delivers.
set -euo pipefail
umask 077
root=/srv/caf settings=/etc/caf/watch.env
while (($#)); do
    case $1 in
        --root) root=${2:?}; shift 2;;
        --settings) settings=${2:?}; shift 2;;
        *) echo 'Unknown watch option' >&2; exit 1;;
    esac
done
command -v jq >/dev/null
command -v flock >/dev/null
root=$(realpath -e -- "$root")
exec 9> "$root/.deployment.lock"
# An upgrade, restore or backup legitimately stops services; staying quiet then avoids false alarms.
flock -n 9 || { echo 'Deployment lock is held; skipping this check'; exit 0; }
receipt=$root/installation.json
test -f "$receipt" && test "$(jq -er .phase "$receipt")" = active || { echo 'No active installation; nothing to watch'; exit 0; }
current=$(realpath -e -- "$root/current-compose.json")
project=$(jq -er .project "$receipt")
port=$(jq -er '.services.web.ports[0].published' "$current")
ready=--not-ready
if curl -fsS --max-time 5 "http://127.0.0.1:$port/api/v1/ready" >/dev/null 2>&1; then ready=--ready; fi
compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$current" "$@"; }
notifications=$(compose run --rm -T --no-deps --entrypoint caf-host web _watch check "$ready")
webhook=
if test -f "$settings"; then
    # shellcheck disable=SC1090
    webhook=$(set -a; . "$settings"; printf '%s' "${CAF_WATCH_WEBHOOK_URL:-}")
fi
host=$(hostname)
jq -c '.[]' <<< "$notifications" | while read -r item; do
    text="[$host] $(jq -r '.kind | ascii_upcase' <<< "$item") $(jq -r .code <<< "$item"): $(jq -r .message <<< "$item")"
    echo "$text"
    if test -n "$webhook"; then
        curl -fsS --max-time 10 -H "Title: CA Final Companion" -d "$text" "$webhook" >/dev/null \
            || echo 'Notification delivery failed' >&2
    fi
done
