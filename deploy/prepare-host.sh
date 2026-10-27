#!/bin/bash
# Owner-authenticated OS setup only: no disk formatting, package changes or app startup.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run this reviewed setup script with sudo on Ubuntu' >&2; exit 1; }
test "$(uname -s)" = Linux && grep -qx 'ID=ubuntu' /etc/os-release \
    && grep -qx 'VERSION_ID="26.04"' /etc/os-release || { echo 'This setup targets Ubuntu 26.04 only' >&2; exit 1; }
if (($#)); then
    test "$#" = 2 && test "$1" = --config || { echo 'Usage: prepare-host.sh [--config PRIVATE_ENV_FILE]' >&2; exit 1; }
fi
getent passwd cafdeploy >/dev/null
getent group cafdeploy >/dev/null
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
systemd-analyze verify "$directory/caf.service"
for path in /srv/caf /opt/caf /etc/caf; do
    test ! -L "$path" || { echo 'Refusing symlinked system destination' >&2; exit 1; }
    if test -e "$path"; then
        test -d "$path" || { echo 'System destination is not a directory' >&2; exit 1; }
        if test "$path" != /etc/caf; then
            test "$(stat -c %U "$path")" = cafdeploy || { echo 'Existing application directory has another owner; preserved for inspection' >&2; exit 1; }
        fi
    elif test "$path" = /etc/caf; then
        install -d -o root -g cafdeploy -m 0750 "$path"
    else
        install -d -o cafdeploy -g cafdeploy -m 0750 "$path"
    fi
done
if test "$#" = 2; then
    source=$(realpath -e -- "$2")
    test "$(stat -c %a "$source")" = 600 && test "$(stat -c %U "$source")" = cafdeploy || {
        echo 'Private configuration must be owned by cafdeploy with mode 0600' >&2; exit 1;
    }
    if test -e /etc/caf/compose.env; then
        cmp -s "$source" /etc/caf/compose.env || { echo 'Existing production configuration preserved; inspect it separately' >&2; exit 1; }
    else
        install -o cafdeploy -g cafdeploy -m 0600 "$source" /etc/caf/compose.env
    fi
fi
if test -e /etc/systemd/system/caf.service; then
    cmp -s "$directory/caf.service" /etc/systemd/system/caf.service || { echo 'Existing application unit preserved; inspect it separately' >&2; exit 1; }
else
    install -o root -g root -m 0644 "$directory/caf.service" /etc/systemd/system/caf.service
fi
systemctl daemon-reload
systemctl enable caf.service
echo 'Application directories and boot unit prepared. No application service started.'
