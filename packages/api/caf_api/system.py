"""Administrator observability: health, recovery snapshot status and model evaluation."""
from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from caf_api.responses import (
    BackupList, ModelEvaluation, SystemHealth,
)
from caf_common.settings import get_settings
from caf_api.deps import get_operations_db
from caf_api.auth import Principal, require_account, require_admin


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_account)])


# ==============================================================================
# System Observability & Hardening Endpoints (Milestone 8)
# ==============================================================================
@router.get("/system/health", response_model=SystemHealth)
def api_get_system_health(session: Session = Depends(get_operations_db), account: Principal = Depends(require_admin)):
    """Retrieve overall system health and active operational alarms."""
    from caf_common.alarms import get_system_health

    health = get_system_health(session)
    return {
        "status": health.overall_status,
        "evaluated_at": health.evaluated_at.isoformat(),
        "alarms": [
            {
                "code": a.code,
                "level": a.level,
                "message": a.message,
                "details": a.details,
            }
            for a in health.alarms
        ],
    }


@router.get("/system/backups", response_model=BackupList)
def api_list_backups(account: Principal = Depends(require_admin)):
    """Read-only view of the recovery snapshots produced by `caf-host backup`.

    Creating, verifying and pruning snapshots is a host operation; the web application
    exposes no write path and no server filesystem locations.
    """
    from caf_common.backup import list_backups
    from caf_common.backup_status import read_status

    backups = list_backups()
    status = read_status(Path(get_settings().storage.backup_dir))
    schedule = None
    if status is not None:
        snapshot = status.get("snapshot") or {}
        schedule = {
            "state": status["state"], "last_attempt_at": status["last_attempt_at"],
            "last_success_at": status.get("last_success_at"), "snapshot": snapshot.get("name"),
            "encryption": status.get("encryption", "not_configured"), "error": status.get("error"),
            "file_integrity_verified": snapshot.get("file_integrity_verified", False),
            "restore_verified": snapshot.get("restore_verified", False),
        }
    return {
        "count": len(backups),
        "backups": [
            {"name": b["name"], "size_mb": b["size_mb"], "age_hours": b["age_hours"],
             "created_at": b["created_at"].isoformat()}
            for b in backups
        ],
        "schedule": schedule,
    }


@router.get("/system/model-evaluation", response_model=ModelEvaluation)
def api_evaluate_models(
    threshold: float = 0.80,
    min_samples: int = 5,
    session: Session = Depends(get_operations_db), account: Principal = Depends(require_admin),
):
    """Evaluate classifier performance against reviewed human decisions."""
    from caf_l3.evaluate import evaluate_model_on_reviewed_decisions

    report = evaluate_model_on_reviewed_decisions(
        session=session,
        bucket_a_threshold=threshold,
        min_samples=min_samples,
    )
    return {
        "total_reviewed": report.total_reviewed,
        "top1_matches": report.top1_matches,
        "top1_agreement": report.top1_agreement,
        "bucket_metrics": {
            b: {
                "bucket": m.bucket,
                "total": m.total,
                "matched": m.matched,
                "precision": m.precision,
            }
            for b, m in report.bucket_metrics.items()
        },
        "bucket_a_threshold": report.bucket_a_threshold,
        "passed": report.passed,
        "status_note": report.status_note,
        "evaluated_at": report.evaluated_at.isoformat(),
    }
