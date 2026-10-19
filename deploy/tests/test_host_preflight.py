"""Preflight fails visibly on incomplete evidence and emits only selected host fields."""

import json

import pytest
from typer.testing import CliRunner

from caf_cli.host import app, inspect_host
from test_release_bundle import bundle_fixture


@pytest.fixture
def inspection(tmp_path):
    values = {
        "os": 'ID=ubuntu\nVERSION_ID="26.04"\nEMPTY=""\n',
        "architecture": "x86_64\n", "cpu": "12\n",
        "memory": "MemTotal: 15564144 kB\nMemAvailable: 14000000 kB\n",
        "storage": "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk 500000000 10000000 400000000 2% /\n",
        "docker": "29.9.1\n", "compose": "5.5.1\n",
        "tailscale": json.dumps({"BackendState": "Running", "Self": {"Online": True},
            "AuthURL": "https://login.invalid/DO_NOT_EXPORT", "Peer": {"private": "DO_NOT_EXPORT"},
            "Health": ["DO_NOT_EXPORT"], "User": {"mail": "DO_NOT_EXPORT"}}),
        "backup_mount": json.dumps({"filesystems": [{"target": "/mnt/caf-backup", "source": "/dev/sdb1", "fstype": "ext4"}]}),
        "clock": "Timezone=Asia/Kolkata\nNTPSynchronized=yes\n",
        "services": "\n\n".join(f"Id={name}.service\nActiveState=active\nUnitFileState=enabled" for name in ("docker", "tailscaled", "ssh")),
        "firewall": "Status: active\n",
        "suspend": "# HandleLidSwitch=suspend\n[Login]\nHandleLidSwitch=ignore\n",
        "power": "ADP0 type Mains\nADP0 online 1\nBAT0 type Battery\nBAT0 status Not charging\nBAT0 capacity 90\n",
        "temperature": "thermal_zone0 45000\n",
        "users": "rvabhi:1000:1000:/home/rvabhi:/bin/bash\ncafdeploy:1001:1001:/home/cafdeploy:/bin/bash\ngdm-greeter:60578:975:/run/gdm3/home/gdm-greeter:/usr/sbin/nologin\n",
        "filesystem": '{"filesystems": [{"target":"/", "source":"/dev/disk", "fstype":"ext4"}]}',
        "disks": '{"blockdevices": []}', "containers": "", "listeners": "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n",
        "layout": "MISSING /srv/caf/data\n",
    }
    for name, value in values.items():
        (tmp_path / f"{name}.out").write_text(value)
        (tmp_path / f"{name}.code").write_text("0\n")
        (tmp_path / f"{name}.err").write_text("DO_NOT_EXPORT")
    (tmp_path / "collected_at").write_text("2026-10-19T12:00:00Z\n")
    return tmp_path


def test_private_snapshot_becomes_non_secret_report(inspection, monkeypatch):
    monkeypatch.setenv("UNRELATED_SECRET", "DO_NOT_EXPORT")
    result = CliRunner().invoke(app, ["preflight", "--inspection", str(inspection)])
    assert result.exit_code == 0, result.output
    assert "DO_NOT_EXPORT" not in result.output
    report = json.loads(result.output)
    assert report["platform"] == "linux/amd64" and report["cpu_threads"] == 12
    assert report["external_backup_mounted"] is True
    assert [item["name"] for item in report["observations"]["login_accounts"]] == ["rvabhi", "cafdeploy"]
    assert report["observations"]["greeter_accounts"][0]["shell"] == "/usr/sbin/nologin"
    assert "Measured internet upload/download" in report["unverified"]


@pytest.mark.parametrize("code, target", [(1, "/mnt/caf-backup"), (0, "/")])
def test_missing_drive_cannot_be_confused_with_root_filesystem(inspection, code, target):
    (inspection / "backup_mount.code").write_text(str(code))
    (inspection / "backup_mount.out").write_text(json.dumps({"filesystems": [{"target": target}]}))
    report = inspect_host(inspection)
    assert report.external_backup_mounted is False
    assert "BACKUP_DRIVE" in {item.code for item in report.findings}
    assert CliRunner().invoke(app, ["preflight", "--inspection", str(inspection)]).exit_code == 2


def test_stopped_tailscale_and_low_space_are_blockers(inspection):
    (inspection / "tailscale.out").write_text('{"BackendState":"Stopped","Self":null}')
    (inspection / "storage.out").write_text("header\n/dev/disk 20000000 19000000 1000000 95% /\n")
    report = inspect_host(inspection)
    assert report.tailscale_online is None
    assert {item.code for item in report.findings if item.level == "blocker"} == {"TAILSCALE", "INITIAL_FREE_SPACE"}


def test_permission_limited_probes_are_unverified(inspection):
    (inspection / "firewall.code").write_text("1")
    report = inspect_host(inspection)
    assert report.observations["firewall"].startswith("unverified")
    assert "FIREWALL_UNVERIFIED" in {item.code for item in report.findings}


def test_required_probe_timeout_is_a_failure(inspection):
    (inspection / "storage.code").write_text("124")
    result = CliRunner().invoke(app, ["preflight", "--inspection", str(inspection)])
    assert result.exit_code == 1
    assert "storage (exit 124)" in result.output
    assert "DO_NOT_EXPORT" not in result.output


def test_host_bundle_verification_uses_existing_contract(tmp_path):
    bundle = bundle_fixture(tmp_path)
    runner = CliRunner()
    base = ["verify-bundle", str(bundle), "--platform", "linux/amd64"]
    assert runner.invoke(app, base).exit_code == 1
    assert runner.invoke(app, base + ["--allow-candidate"]).exit_code == 0
    assert runner.invoke(app, ["verify-bundle", str(bundle), "--platform", "linux/arm64", "--allow-candidate"]).exit_code == 1
