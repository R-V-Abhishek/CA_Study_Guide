"""System health observability and alarms evaluation engine."""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.backup import list_backups
from caf_common.settings import get_settings
from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion
from caf_db.models.ops import Run

logger = logging.getLogger(__name__)


@dataclass
class Alarm:
    code: str
    level: str  # OK | WARNING | CRITICAL
    message: str
    details: dict[str, Any]


@dataclass
class SystemHealthReport:
    overall_status: str  # OK | WARNING | CRITICAL
    alarms: list[Alarm]
    evaluated_at: datetime


def evaluate_system_alarms(
    session: Session,
    backup_dir: Path | str | None = None,
    max_backup_age_hours: float = 48.0,
) -> list[Alarm]:
    """Evaluate all system alarms specified in Section 6.6 of the specification:
    
    1. BACKUP_STALE: Backup older than 48 hours or absent
    2. ZERO_LINKS_DISCOVERED: Seed discovery returned 0 links
    3. EXTRACTION_FAILURE_HIGH: Extraction failure rate above 20% in latest run
    4. BUDGET_CAP_REACHED: Budget cap exceeded or run aborted due to budget
    5. BUCKET_A_PRECISION_DROP: Bucket A human acceptance precision below threshold
    """
    alarms: list[Alarm] = []

    # 1. Check Backup Freshness
    backups = list_backups(backup_dir)
    if not backups:
        alarms.append(
            Alarm(
                code="BACKUP_STALE",
                level="WARNING",
                message="No database backups found in backup directory",
                details={"last_backup_age_hours": None, "total_backups": 0},
            )
        )
    else:
        latest = backups[0]
        age = latest["age_hours"]
        if age > max_backup_age_hours:
            alarms.append(
                Alarm(
                    code="BACKUP_STALE",
                    level="WARNING",
                    message=f"Latest backup '{latest['name']}' is {age} hours old (> {max_backup_age_hours}h threshold)",
                    details={"last_backup_age_hours": age, "latest_file": latest["name"]},
                )
            )
        else:
            alarms.append(
                Alarm(
                    code="BACKUP_OK",
                    level="OK",
                    message=f"Latest backup '{latest['name']}' is fresh ({age}h old)",
                    details={"last_backup_age_hours": age, "latest_file": latest["name"]},
                )
            )

    # 2. Check Zero Links Discovered
    latest_discover_run = (
        session.query(Run)
        .filter(Run.stage == "l1.discover")
        .order_by(Run.id.desc())
        .first()
    )
    if latest_discover_run and latest_discover_run.stats:
        total_discovered = latest_discover_run.stats.get("total_discovered", 0)
        if total_discovered == 0:
            alarms.append(
                Alarm(
                    code="ZERO_LINKS_DISCOVERED",
                    level="WARNING",
                    message=f"Latest discovery run #{latest_discover_run.id} found 0 new links",
                    details={"run_id": latest_discover_run.id, "stats": latest_discover_run.stats},
                )
            )

    # 3. Check Extraction Failure Rate
    latest_extract_run = (
        session.query(Run)
        .filter(Run.stage == "extract")
        .order_by(Run.id.desc())
        .first()
    )
    if latest_extract_run:
        # Check documents for this extract run or overall
        docs = session.query(Document).filter(Document.extract_run_id == latest_extract_run.id).all()
        if docs:
            total_docs = len(docs)
            failed_docs = sum(1 for d in docs if d.extract_status == "failed")
            failure_rate = failed_docs / total_docs
            if failure_rate > 0.20:
                alarms.append(
                    Alarm(
                        code="EXTRACTION_FAILURE_HIGH",
                        level="WARNING",
                        message=f"Extraction failure rate is {failure_rate * 100:.1f}% (> 20%) in run #{latest_extract_run.id}",
                        details={"run_id": latest_extract_run.id, "total": total_docs, "failed": failed_docs, "rate": round(failure_rate, 3)},
                    )
                )

    # 4. Check Budget Cap
    budget_aborted_run = (
        session.query(Run)
        .filter(Run.status == "aborted_budget")
        .order_by(Run.id.desc())
        .first()
    )
    if budget_aborted_run:
        alarms.append(
            Alarm(
                code="BUDGET_CAP_REACHED",
                level="CRITICAL",
                message=f"Run #{budget_aborted_run.id} was aborted due to LLM budget cap being reached",
                details={"run_id": budget_aborted_run.id, "stage": budget_aborted_run.stage},
            )
        )

    # 5. Check Bucket A Precision Drop
    # Join decisions with TagSuggestion on bucket A
    recent_decisions = (
        session.query(Decision, TagSuggestion)
        .join(TagSuggestion, TagSuggestion.unit_id == Decision.id)
        .filter(TagSuggestion.bucket == "A")
        .order_by(Decision.id.desc())
        .limit(100)
        .all()
    )
    if len(recent_decisions) >= 10:
        accepted = sum(1 for d, _ in recent_decisions if d.action in ("accept", "bulk_accept"))
        precision = accepted / len(recent_decisions)
        if precision < 0.80:
            alarms.append(
                Alarm(
                    code="BUCKET_A_PRECISION_DROP",
                    level="WARNING",
                    message=f"Bucket A precision dropped to {precision * 100:.1f}% (< 80% threshold across {len(recent_decisions)} decisions)",
                    details={"precision": round(precision, 3), "samples": len(recent_decisions)},
                )
            )

    return alarms


def get_system_health(
    session: Session,
    backup_dir: Path | str | None = None,
) -> SystemHealthReport:
    """Evaluate alarms and produce overall system health report."""
    alarms = evaluate_system_alarms(session, backup_dir=backup_dir)
    overall_status = "OK"
    for a in alarms:
        if a.level == "CRITICAL":
            overall_status = "CRITICAL"
            break
        elif a.level == "WARNING" and overall_status != "CRITICAL":
            overall_status = "WARNING"

    return SystemHealthReport(
        overall_status=overall_status,
        alarms=alarms,
        evaluated_at=datetime.now(timezone.utc),
    )
