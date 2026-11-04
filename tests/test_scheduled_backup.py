"""Scheduled snapshots: retention policy, status record and failure containment."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from caf_cli import host_backup
from caf_common.retention import plan_retention, snapshot_time


def identifier(moment: datetime, suffix: str = "deadbeef") -> str:
    return f"caf_{moment:%Y%m%d_%H%M%S_%f}_{suffix}"


def test_retention_keeps_one_per_day_week_and_month_and_always_the_newest():
    start = datetime(2026, 10, 31, 15, 30, tzinfo=timezone.utc)
    # Two snapshots on each of 200 calendar days: 15:30 (newest of its day) and 03:30.
    ids = [
        identifier(start - timedelta(days=day, hours=hours))
        for day in range(200)
        for hours in (0, 12)
    ]
    keep, delete = plan_retention(ids, daily=7, weekly=4, monthly=6)
    assert keep[0] == identifier(start)
    assert set(keep) | set(delete) == set(ids) and not set(keep) & set(delete)
    days = {snapshot_time(i).date() for i in keep}
    assert all((start - timedelta(days=d)).date() in days for d in range(7))
    assert len(keep) <= 7 + 4 + 6
    # Each retained day keeps its newest snapshot, not an arbitrary one.
    assert identifier(start - timedelta(days=3)) in keep
    assert not any(snapshot_time(i).hour == 3 for i in keep)


def test_retention_with_few_snapshots_keeps_everything():
    ids = [
        identifier(datetime(2026, 10, 29 + n, 3, 0, tzinfo=timezone.utc), f"{n:08x}")
        for n in range(3)
    ]
    assert plan_retention(ids)[1] == []


def test_retention_never_prunes_a_protected_rollback_snapshot():
    day = datetime(2026, 11, 4, tzinfo=timezone.utc)
    before_upgrade = identifier(day.replace(hour=2, minute=30), "00000001")
    after_upgrade = identifier(day.replace(hour=3, minute=15), "00000002")
    assert plan_retention([before_upgrade, after_upgrade])[1] == [before_upgrade]
    keep, delete = plan_retention(
        [before_upgrade, after_upgrade], protected=frozenset({before_upgrade, "caf_missing"})
    )
    assert before_upgrade in keep and delete == []


def test_retention_rejects_foreign_names_and_empty_tiers():
    with pytest.raises(ValueError, match="Not a recovery snapshot"):
        plan_retention(["caf_notes"])
    with pytest.raises(ValueError, match="at least one"):
        plan_retention([identifier(datetime.now(timezone.utc))], daily=0)


def fake_snapshot(base, moment, manifest=True):
    directory = base / identifier(moment)
    directory.mkdir()
    if manifest:
        (directory / "manifest.json").write_text("{}")
    return directory


def test_scheduled_backup_writes_status_and_prunes_only_verified_old_snapshots(session, tmp_path):
    now = datetime.now(timezone.utc)
    old = [fake_snapshot(tmp_path, now - timedelta(days=400 + n)) for n in range(3)]
    unverified = fake_snapshot(tmp_path, now - timedelta(days=500), manifest=False)
    foreign = tmp_path / "keep-me"
    foreign.mkdir()
    status = host_backup.run_backup(tmp_path, daily=1, weekly=1, monthly=1, session=session)
    assert status["state"] == "ok" and status["error"] is None
    assert (
        status["snapshot"]["file_integrity_verified"] is True
        and status["snapshot"]["restore_verified"] is False
    )
    assert (tmp_path / status["snapshot"]["name"] / "manifest.json").is_file()
    assert (
        json.loads((tmp_path / "status.json").read_text())["snapshot"]["name"]
        == status["snapshot"]["name"]
    )
    assert status["retained"][0] == status["snapshot"]["name"]
    # One slot per tier: the new snapshot plus at most one older week and one older month survive.
    assert 1 <= len(status["retained"]) <= 3
    assert sorted(path.name for path in old if path.exists()) == sorted(
        name for name in status["retained"] if name != status["snapshot"]["name"]
    )
    assert sorted(status["deleted"]) == sorted(path.name for path in old if not path.exists())
    assert unverified.exists() and foreign.exists()


def test_failed_backup_prunes_nothing_and_preserves_the_last_success(
    session, tmp_path, monkeypatch
):
    now = datetime.now(timezone.utc)
    kept = fake_snapshot(tmp_path, now - timedelta(days=1))
    older = fake_snapshot(tmp_path, now - timedelta(days=900))
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "last_success_at": "2026-10-31T03:30:00+00:00",
                "snapshot": {"name": kept.name},
                "retained": [kept.name],
                "encryption": "not_configured",
            }
        )
    )

    def broken(**_):
        raise RuntimeError("pg_dump exploded")

    monkeypatch.setattr(host_backup, "create_backup", broken)
    with pytest.raises(RuntimeError, match="pg_dump exploded"):
        host_backup.run_backup(tmp_path, daily=1, weekly=1, monthly=1, session=session)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "failed" and "pg_dump exploded" in status["error"]
    assert status["last_success_at"] == "2026-10-31T03:30:00+00:00" and status["snapshot"] == {
        "name": kept.name
    }
    assert kept.exists() and older.exists()
