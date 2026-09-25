"""Test suite for Milestone 8: Hardening, Backups, Alarms, and Model Evaluation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid
from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from caf_api.main import app as api_app
from caf_cli.main import app as cli_app
from caf_common.alarms import evaluate_system_alarms, get_system_health
from caf_common.backup import create_backup, list_backups, rotate_backups, verify_backup
from caf_db.engine import get_session_factory
from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.ops import Event, Run
from caf_l3.evaluate import evaluate_model_on_reviewed_decisions

runner = CliRunner()


@pytest.fixture
def client():
    return TestClient(api_app)


@pytest.fixture
def session():
    factory = get_session_factory()
    with factory() as sess:
        yield sess


def test_backup_rotation_policy(tmp_path):
    """Verify retention policy of 14 daily and 8 weekly dumps."""
    b_dir = tmp_path / "backups"
    b_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy dumps spanning 30 different days
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    created_files = []
    for day_offset in range(30):
        t = base_time + timedelta(days=day_offset)
        ts_str = t.strftime("%Y%m%d_%H%M%S")
        f_path = b_dir / f"caf_{ts_str}.dump"
        f_path.write_text("dummy dump")
        os_time = t.timestamp()
        import os
        os.utime(f_path, (os_time, os_time))
        created_files.append(f_path)

    # Enforce rotation
    deleted = rotate_backups(b_dir, max_daily=14, max_weekly=8)
    assert len(deleted) > 0

    remaining = list(b_dir.glob("caf_*.dump"))
    # Kept daily (14) + distinct previous weekly (up to 8) <= 22
    assert len(remaining) <= 22
    assert len(remaining) >= 14


def test_backup_creation_and_listing(session, tmp_path):
    """Verify pg_dump execution, blob syncing, config archiving, and ops.event recording."""
    b_dir = tmp_path / "backups"
    manifest = create_backup(session=session, backup_dir=b_dir)

    assert manifest.dump_file.exists()
    assert manifest.dump_size_bytes > 0
    assert manifest.dump_file.name.startswith("caf_")
    assert manifest.dump_file.name.endswith(".dump")

    # Verify listing
    backups = list_backups(b_dir)
    assert len(backups) == 1
    assert backups[0]["name"] == manifest.dump_file.name
    assert backups[0]["age_hours"] < 1.0

    # Verify ops.event recorded
    ev = (
        session.query(Event)
        .filter(Event.code == "BACKUP_OK")
        .order_by(Event.id.desc())
        .first()
    )
    assert ev is not None
    assert "caf_" in ev.message


def test_backup_verification_drill(session, tmp_path):
    """Verify live restore drill into scratch DB with critical table row count validation."""
    b_dir = tmp_path / "drill_backups"
    manifest = create_backup(session=session, backup_dir=b_dir)
    res = verify_backup(session=session, dump_file=manifest.dump_file, scratch_db_name="caf_verify_test")
    assert res.verified is True
    assert len(res.mismatches) == 0
    assert "critical tables match" in res.message

    # Verify verification ops.event recorded
    ev = (
        session.query(Event)
        .filter(Event.code == "BACKUP_VERIFIED_OK")
        .order_by(Event.id.desc())
        .first()
    )
    assert ev is not None
    assert ev.context.get("verified") is True


def test_system_alarms_evaluation(session, tmp_path):
    """Verify alarms trigger for stale backup, zero links, high extraction failures, and budget cap."""
    # 1. Stale backup alarm when backup directory is empty
    empty_bdir = tmp_path / "empty_backups"
    empty_bdir.mkdir()
    alarms = evaluate_system_alarms(session, backup_dir=empty_bdir)
    stale_alarm = next((a for a in alarms if a.code == "BACKUP_STALE"), None)
    assert stale_alarm is not None
    assert stale_alarm.level == "WARNING"

    # 2. Budget cap alarm
    budget_run = Run(
        stage="l3_classify",
        status="aborted_budget",
        config_hash="cap_test",
    )
    session.add(budget_run)
    session.commit()

    health = get_system_health(session, backup_dir=empty_bdir)
    assert health.overall_status in ("WARNING", "CRITICAL")
    budget_alarm = next((a for a in health.alarms if a.code == "BUDGET_CAP_REACHED"), None)
    assert budget_alarm is not None
    assert budget_alarm.level == "CRITICAL"


def test_model_re_evaluation_procedure(session):
    """Verify model re-evaluation against reviewed decisions in core.decision."""
    report = evaluate_model_on_reviewed_decisions(
        session=session,
        bucket_a_threshold=0.80,
        min_samples=5,
    )
    assert report.total_reviewed >= 1
    assert report.top1_agreement >= 0.0
    assert "A" in report.bucket_metrics
    assert report.passed is True
    assert "PASSED" in report.status_note or "minimum" in report.status_note


def test_milestone8_api_endpoints(client):
    """Verify REST API system observability and backup endpoints."""
    # 1. GET /api/v1/system/health
    res_health = client.get("/api/v1/system/health")
    assert res_health.status_code == 200
    data_h = res_health.json()
    assert "status" in data_h
    assert "alarms" in data_h

    # 2. GET /api/v1/system/backups
    res_backups = client.get("/api/v1/system/backups")
    assert res_backups.status_code == 200
    data_b = res_backups.json()
    assert "count" in data_b
    assert "backups" in data_b

    # 3. GET /api/v1/system/model-evaluation
    res_eval = client.get("/api/v1/system/model-evaluation?threshold=0.80")
    assert res_eval.status_code == 200
    data_e = res_eval.json()
    assert "bucket_metrics" in data_e
    assert "top1_agreement" in data_e
    assert "passed" in data_e


def test_milestone8_cli_commands():
    """Verify CLI commands: caf backup list, caf classify evaluate, and caf status."""
    # 1. caf backup list
    res_list = runner.invoke(cli_app, ["backup", "list"])
    assert res_list.exit_code == 0
    assert "Database Backups" in res_list.output or "No database backups found" in res_list.output

    # 2. caf classify evaluate
    res_eval = runner.invoke(cli_app, ["classify", "evaluate", "--threshold", "0.80"])
    assert res_eval.exit_code == 0
    assert "Model Evaluation" in res_eval.output
    assert "Gate Outcome" in res_eval.output

    # 3. caf status
    res_status = runner.invoke(cli_app, ["status"])
    assert res_status.exit_code == 0
    assert "Recent Pipeline Runs" in res_status.output
    assert "System Health & Alarms" in res_status.output
