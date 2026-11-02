#!/usr/bin/env bash
# Diagnose and restore remote access (SSH over Tailscale) to the home server. Run it at the machine's
# console with sudo. Without --apply it only reads; --apply makes the fixes listed at the bottom.
# It never touches Docker, the CAF services, application data or the Tailscale login.
set -uo pipefail

apply=0
test "${1:-}" = --apply && apply=1
test "$(id -u)" = 0 || { echo "Run with sudo." >&2; exit 1; }
section() { printf '\n== %s\n' "$*"; }

section "Uptime and power"
uptime -p
last -x -n 4 reboot shutdown 2>/dev/null | head -4
for supply in /sys/class/power_supply/*; do
    test -r "$supply/type" || continue
    printf '%s %s %s%%\n' "$(basename "$supply")" "$(cat "$supply/status" 2>/dev/null || cat "$supply/online")" "$(cat "$supply/capacity" 2>/dev/null)"
done

section "Sleep and lid policy"
for target in sleep suspend hibernate; do
    printf '%s.target: %s\n' "$target" "$(systemctl is-enabled "$target.target" 2>&1)"
done
systemd-analyze cat-config systemd/logind.conf 2>/dev/null | grep -E '^(HandleLid|IdleAction)' || echo "logind: defaults (lid close suspends)"

section "Network"
ip -br address | grep -v '^lo '
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>/dev/null
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "internet: up" || echo "internet: DOWN"
getent hosts controlplane.tailscale.com >/dev/null && echo "dns: ok" || echo "dns: FAILED"

section "Services"
for unit in ssh tailscaled docker caf; do
    printf '%s: %s\n' "$unit" "$(systemctl is-active "$unit" 2>&1)"
done
tailscale status 2>&1 | head -4
journalctl -b -p warning --no-pager -n 12 -u tailscaled -u ssh -u NetworkManager 2>/dev/null | cut -c1-200

if test "$apply" = 0; then
    printf '\nRead only. Run again with --apply to: restart NetworkManager and tailscaled, enable ssh, make Wi-Fi\n'
    printf 'connections available before login, and stop lid-close and idle suspend.\n'
    exit 0
fi

section "Applying"
systemctl enable --now ssh tailscaled
nmcli -t -f NAME,TYPE connection show 2>/dev/null | while IFS=: read -r name type; do
    case "$type" in
    *wireless*) nmcli connection modify "$name" connection.autoconnect yes connection.permissions "" && echo "wifi available to all users: $name" ;;
    esac
done
install -d /etc/systemd/logind.conf.d
cat >/etc/systemd/logind.conf.d/50-caf-always-on.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl kill -s HUP systemd-logind
systemctl restart NetworkManager
sleep 10
systemctl restart tailscaled
sleep 8

section "Result"
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "internet: up" || echo "internet: DOWN"
tailscale status 2>&1 | head -4
tailscale ip -4 2>&1 | head -1
