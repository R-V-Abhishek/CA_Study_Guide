#!/bin/sh
# Collect known, read-only Ubuntu probes. Output is private transient input, not a report.
set -eu
if [ "$#" -ne 1 ] || [ "$(uname -s)" != Linux ]; then
    echo 'Usage on Ubuntu: sh deploy/collect-host.sh EMPTY_PRIVATE_DIRECTORY' >&2
    exit 1
fi
out=$1
if [ ! -d "$out" ] || [ -n "$(ls -A "$out")" ]; then
    echo 'Collector destination must be an existing empty directory' >&2
    exit 1
fi
umask 077
probe() {
    name=$1
    shift
    code=0
    timeout 12 "$@" > "$out/$name.out" 2> "$out/$name.err" || code=$?
    printf '%s\n' "$code" > "$out/$name.code"
}
probe os cat /etc/os-release
probe architecture uname -m
probe cpu getconf _NPROCESSORS_ONLN
probe memory cat /proc/meminfo
probe storage df -Pk /srv
probe filesystem findmnt --json --mountpoint / --output TARGET,SOURCE,FSTYPE
probe disks lsblk --json --output NAME,TYPE,FSTYPE,MOUNTPOINTS,SIZE
probe clock timedatectl show --property=NTPSynchronized --property=Timezone
probe services systemctl show docker.service tailscaled.service ssh.service --property=Id --property=ActiveState --property=UnitFileState
probe docker docker version --format '{{.Server.Version}}'
probe compose docker compose version --short
probe containers docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Image}}'
probe tailscale tailscale status --json
probe firewall ufw status verbose
probe listeners ss -H -lnt
probe backup_mount findmnt --json --mountpoint /mnt/caf-backup --output TARGET,SOURCE,FSTYPE
probe suspend systemd-analyze cat-config systemd/logind.conf
probe users sh -c 'getent passwd | awk -F: '\''{print $1 ":" $3 ":" $4 ":" $6 ":" $7}'\'''
probe power sh -c '
for p in /sys/class/power_supply/*; do
    test -d "$p" || continue
    for name in type online status capacity energy_full energy_full_design charge_full charge_full_design cycle_count; do
        if test -r "$p/$name"; then
            printf "%s %s " "${p##*/}" "$name"
            cat "$p/$name"
        fi
    done
done'
probe temperature sh -c '
for p in /sys/class/thermal/thermal_zone*; do
    test -r "$p/temp" || continue
    printf "%s " "${p##*/}"
    cat "$p/temp"
done'
probe layout sh -c '
for p in /opt/caf/repo /srv/caf/postgres /srv/caf/data /srv/caf/releases /srv/caf/backups /etc/caf; do
    if test -e "$p"; then stat -c "%a %U:%G %n" "$p"; else printf "MISSING %s\n" "$p"; fi
done'
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/collected_at"
