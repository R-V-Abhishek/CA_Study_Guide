# shellcheck shell=bash
# Shared by host scripts, which set -euo pipefail before sourcing it.
# Not every older script uses it yet (finding L-06 in docs/Code_review_2026_11_06.md).

# A one-off container of an installed image: no network, no privileges, read-only root.
sandbox=(--rm --pull=never --network none --read-only --cap-drop ALL
    --security-opt no-new-privileges:true --pids-limit 64 --cpus 1)

# Sets receipt, project, current (the effective Compose file) and image for an ACTIVE installation.
active_installation() {
    receipt=$1/installation.json
    test -f "$receipt" && test "$(jq -er .phase "$receipt")" = active || { echo 'An active installation is required' >&2; exit 1; }
    test ! -e "$1/.upgrade-in-progress" || { echo 'A previous upgrade did not finish; read its failure.json first' >&2; exit 1; }
    test -L "$1/current-compose.json" || { echo 'Current deployment pointer is missing' >&2; exit 1; }
    current=$(realpath -e -- "$1/current-compose.json")
    project=$(jq -er .project "$receipt")
    image=$(jq -er .services.web.image "$current")
}

compose() { env -i PATH="$PATH" HOME="$HOME" docker compose --env-file /dev/null -p "$project" -f "$current" "$@"; }
