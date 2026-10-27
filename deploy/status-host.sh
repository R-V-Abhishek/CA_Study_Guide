#!/bin/bash
set -euo pipefail
root=/srv/caf
if (($#)); then
    test "$#" = 2 && test "$1" = --root || { echo 'Usage: caf-host status [--root DIRECTORY]' >&2; exit 1; }
    root=$2
fi
receipt=$root/installation.json
test -f "$receipt" || { echo '{"status":"not_installed"}'; exit 2; }
phase=$(jq -er .phase "$receipt")
if test "$phase" != active; then
    jq '{status:"incomplete",phase,application:.application.version,commit:.application.commit}' "$receipt"
    exit 2
fi
project=$(jq -er .project "$receipt")
compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$root/current-compose.json" "$@"; }
running=$(compose ps --services --status running | sort | tr '\n' ' ')
schema=$(compose exec -T db psql -U postgres -d caf -Atc 'SELECT version_num FROM ops.alembic_version' 2>/dev/null) || schema=unavailable
ready=false
if compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/v1/ready', timeout=5).close()" >/dev/null 2>&1; then ready=true; fi
jq --arg schema "$schema" --arg running "$running" --argjson ready "$ready" \
    '{status:(if $ready then "ready" else "not_ready" end),application:.application.version,commit:.application.commit,platform:.application.platform,schema:$schema,running_services:($running|split(" ")|map(select(length>0))),backup:"not_configured",worker_monitoring:"container_state_only"}' "$receipt"
if test "$ready" = true && [[ " $running" == *" worker "* ]]; then exit 0; fi
exit 2
