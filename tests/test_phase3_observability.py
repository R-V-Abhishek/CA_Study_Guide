"""Structured logging, request correlation, worker liveness and de-duplicated alerts."""

from datetime import datetime, timedelta, timezone
import json
import logging

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from caf_api.main import app
from caf_api.security_logging import AUTH_ACCESS_FILTER
from caf_cli.host import app as host_app
from caf_cli.host_watch import check, decide, find_problems
from caf_common.alarms import evaluate_system_alarms
from caf_common.backup_status import write_status
from caf_common.heartbeat import read_heartbeat, write_heartbeat
from caf_common.logging import get_logger, setup_logging
from caf_common.settings import get_settings

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers, root.level = handlers, level
    setup_logging(json=False)


def lines(captured):
    return [json.loads(line) for line in captured.splitlines() if line.startswith("{")]


def test_production_logs_are_json_and_carry_the_request_id(capsys, restore_logging):
    import structlog

    setup_logging(json=True)
    structlog.contextvars.bind_contextvars(request_id="abc123")
    try:
        get_logger("t").info("structured", job=7)
        logging.getLogger("stdlib.module").warning("plain %s", "record")
    finally:
        structlog.contextvars.clear_contextvars()
    records = lines(capsys.readouterr().err)
    assert {"event": "structured", "job": 7, "request_id": "abc123"}.items() <= records[0].items()
    assert records[0]["level"] == "info" and records[0]["timestamp"].endswith("Z")
    assert records[1]["event"] == "plain record" and records[1]["request_id"] == "abc123"
    assert records[1]["logger"] == "stdlib.module"


def test_console_format_stays_readable_outside_production(capsys, restore_logging):
    setup_logging(json=False)
    get_logger("t").info("for people")
    assert "for people" in capsys.readouterr().err and not lines(capsys.readouterr().err)


def test_request_id_is_echoed_when_harmless_and_replaced_otherwise():
    client = TestClient(app)
    assert (
        client.get("/api/v1/health", headers={"X-Request-ID": "client-id_1.2"}).headers[
            "x-request-id"
        ]
        == "client-id_1.2"
    )
    generated = client.get(
        "/api/v1/health", headers={"X-Request-ID": "bad id\twith spaces"}
    ).headers["x-request-id"]
    assert len(generated) == 32 and generated.isalnum()
    assert client.get("/api/v1/health").headers["x-request-id"] != generated


def test_access_log_filter_still_redacts_auth_queries():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/auth/callback?code=secret&state=s", "1.1", 302),
        None,
    )
    AUTH_ACCESS_FILTER.filter(record)
    assert record.args[2] == "/auth/callback"


def test_heartbeat_roundtrip_and_stale_worker_alarm(session, tmp_path):
    assert read_heartbeat(tmp_path) is None
    assert "WORKER_STALE" not in {
        alarm.code for alarm in evaluate_system_alarms(session, backup_dir=tmp_path)
    }
    write_heartbeat(tmp_path, NOW - timedelta(minutes=30))
    stale = [
        alarm
        for alarm in evaluate_system_alarms(session, backup_dir=tmp_path)
        if alarm.code == "WORKER_STALE"
    ]
    assert (
        stale
        and stale[0].level == "CRITICAL"
        and stale[0].details["last_heartbeat_at"].startswith("2026")
    )
    write_heartbeat(tmp_path)
    assert "WORKER_STALE" not in {
        alarm.code for alarm in evaluate_system_alarms(session, backup_dir=tmp_path)
    }


def test_missing_worker_is_a_warning_only_in_production(session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings().app, "env", "production")
    alarms = [
        alarm
        for alarm in evaluate_system_alarms(session, backup_dir=tmp_path)
        if alarm.code == "WORKER_STALE"
    ]
    assert [alarm.level for alarm in alarms] == ["WARNING"]


def healthy_status(at=NOW):
    return {"state": "ok", "last_success_at": at.isoformat(), "last_attempt_at": at.isoformat()}


def test_problem_detection():
    assert find_problems(ready=True, backup=healthy_status(), heartbeat=NOW, now=NOW) == {}
    problems = find_problems(
        ready=False,
        backup={"state": "failed", "error": "disk full"},
        heartbeat=NOW - timedelta(hours=1),
        now=NOW,
    )
    assert (
        set(problems) == {"NOT_READY", "WORKER_STALE", "BACKUP_FAILED"}
        and "disk full" in problems["BACKUP_FAILED"]
    )
    assert "BACKUP_STALE" in find_problems(
        ready=True, backup=healthy_status(NOW - timedelta(hours=49)), heartbeat=NOW, now=NOW
    )
    assert "BACKUP_STALE" in find_problems(ready=True, backup=None, heartbeat=NOW, now=NOW)


def test_each_failure_notifies_exactly_once_then_reminds_daily_and_reports_recovery(tmp_path):
    def at(offset, ready):
        moment = NOW + offset  # a live worker and a fresh snapshot keep reporting throughout
        write_heartbeat(tmp_path, moment)
        write_status(tmp_path, healthy_status(moment))
        return check(tmp_path, ready=ready, now=moment)

    assert at(timedelta(0), True) == []
    first = at(timedelta(minutes=5), False)
    assert [(item["kind"], item["code"]) for item in first] == [("alert", "NOT_READY")]
    assert at(timedelta(minutes=10), False) == []
    assert at(timedelta(hours=23), False) == []
    assert [item["kind"] for item in at(timedelta(hours=25), False)] == ["reminder"]
    recovered = at(timedelta(hours=26), True)
    assert [(item["kind"], item["code"]) for item in recovered] == [("recovered", "NOT_READY")]
    assert at(timedelta(hours=27), True) == []


def test_new_problem_while_another_persists_notifies_only_the_new_one():
    _, state = decide({"NOT_READY": "down"}, {}, NOW)
    notifications, _ = decide(
        {"NOT_READY": "down", "BACKUP_FAILED": "bad"}, state, NOW + timedelta(minutes=5)
    )
    assert [item["code"] for item in notifications] == ["BACKUP_FAILED"]


def test_watch_command_reads_the_configured_snapshot_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings().storage, "backup_dir", tmp_path)
    write_heartbeat(tmp_path)
    write_status(tmp_path, healthy_status(datetime.now(timezone.utc)))
    runner = CliRunner()
    assert json.loads(runner.invoke(host_app, ["_watch", "check", "--ready"]).output) == []
    outage = runner.invoke(host_app, ["_watch", "check", "--not-ready"])
    assert outage.exit_code == 0 and json.loads(outage.output)[0]["code"] == "NOT_READY"
    assert json.loads(runner.invoke(host_app, ["_watch", "check", "--not-ready"]).output) == []
