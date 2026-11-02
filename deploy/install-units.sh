#!/usr/bin/env bash
# Install and start the scheduled backup and health-watch timers. Run with sudo from the repository checkout
# the host uses (/opt/caf/repo). Re-running is safe: units are overwritten with the checked-out versions.
set -euo pipefail

test "$(id -u)" = 0 || { echo "Run with sudo." >&2; exit 1; }
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
units=(caf-backup.service caf-backup.timer caf-watch.service caf-watch.timer)

for unit in "${units[@]}"; do
    install -m 0644 "$here/$unit" "/etc/systemd/system/$unit"
done
systemd-analyze verify "${units[@]/#//etc/systemd/system/}"
systemctl daemon-reload
systemctl enable --now caf-backup.timer caf-watch.timer
systemctl list-timers caf-backup.timer caf-watch.timer --no-pager

test -s /etc/caf/backup-recipient.txt || echo "Note: no /etc/caf/backup-recipient.txt, so backups are not encrypted (status: not_configured)."
test -s /etc/caf/watch.env || echo "Note: no /etc/caf/watch.env with CAF_WATCH_WEBHOOK_URL, so alerts only reach the journal."
