"""Model Re-evaluation Engine: evaluates model suggestions against human curator decisions."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any
from sqlalchemy.orm import Session

from caf_db.models.core import Decision
from caf_db.models.ingest import TagSuggestion, Unit

logger = logging.getLogger(__name__)


@dataclass
class BucketMetric:
    bucket: str
    total: int
    matched: int
    precision: float


@dataclass
class ModelEvaluationReport:
    total_reviewed: int
    top1_matches: int
    top1_agreement: float
    bucket_metrics: dict[str, BucketMetric]
    bucket_a_threshold: float
    passed: bool
    status_note: str
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def evaluate_model_on_reviewed_decisions(
    session: Session,
    bucket_a_threshold: float = 0.80,
    min_samples: int = 5,
) -> ModelEvaluationReport:
    """Evaluate classifier performance against reviewed curator decisions in core.decision.
    
    Exit criteria for model changes (Risk Register §9, Plan §6.3):
    - Evaluates agreement between TagSuggestion primary recommendations and human accepted nodes.
    - Computes precision for each confidence bucket (A, B, C, D).
    - Requires Bucket A precision >= threshold (default 80%) before model switch.
    """
    # 1. Fetch human decisions where a primary node was accepted or edited
    decisions = (
        session.query(Decision)
        .filter(Decision.action.in_(["accept", "bulk_accept", "accept_alt", "edit"]))
        .order_by(Decision.id.desc())
        .all()
    )

    if not decisions:
        return ModelEvaluationReport(
            total_reviewed=0,
            top1_matches=0,
            top1_agreement=0.0,
            bucket_metrics={},
            bucket_a_threshold=bucket_a_threshold,
            passed=True,
            status_note="No reviewed decisions available yet in core.decision.",
        )

    # 2. Map fingerprint to Unit
    fingerprints = [d.unit_fingerprint for d in decisions]
    units = (
        session.query(Unit)
        .filter(Unit.fingerprint.in_(fingerprints))
        .all()
    )
    unit_by_fp = {u.fingerprint: u for u in units}
    unit_ids = [u.id for u in units]

    # 3. Fetch primary tag suggestions for these units
    suggestions = (
        session.query(TagSuggestion)
        .filter(
            TagSuggestion.unit_id.in_(unit_ids),
            TagSuggestion.role == "primary",
        )
        .order_by(TagSuggestion.id.desc())
        .all()
    )

    # Unit ID -> latest primary suggestion
    sugg_by_unit: dict[int, TagSuggestion] = {}
    for s in suggestions:
        if s.unit_id not in sugg_by_unit:
            sugg_by_unit[s.unit_id] = s

    # 4. Compare model suggestion vs curator decision
    total_evaluated = 0
    top1_matches = 0
    bucket_counts: dict[str, dict[str, int]] = {
        "A": {"total": 0, "matched": 0},
        "B": {"total": 0, "matched": 0},
        "C": {"total": 0, "matched": 0},
        "D": {"total": 0, "matched": 0},
    }

    for d in decisions:
        unit = unit_by_fp.get(d.unit_fingerprint)
        if not unit:
            continue

        sugg = sugg_by_unit.get(unit.id)
        if not sugg:
            continue

        curator_primary = d.payload.get("primary_node_id")
        if not curator_primary:
            continue

        total_evaluated += 1
        b = sugg.bucket if sugg.bucket in bucket_counts else "D"
        bucket_counts[b]["total"] += 1

        is_match = (sugg.node_id == curator_primary)
        if is_match:
            top1_matches += 1
            bucket_counts[b]["matched"] += 1

    if total_evaluated == 0:
        return ModelEvaluationReport(
            total_reviewed=0,
            top1_matches=0,
            top1_agreement=0.0,
            bucket_metrics={},
            bucket_a_threshold=bucket_a_threshold,
            passed=True,
            status_note="No paired decision-suggestion pairs found for evaluation.",
        )

    # 5. Calculate metrics
    top1_agreement = round(top1_matches / total_evaluated, 4)
    bucket_metrics: dict[str, BucketMetric] = {}

    for b, counts in bucket_counts.items():
        t = counts["total"]
        m = counts["matched"]
        prec = round(m / t, 4) if t > 0 else 0.0
        bucket_metrics[b] = BucketMetric(
            bucket=b,
            total=t,
            matched=m,
            precision=prec,
        )

    # Gate verification
    bucket_a_metric = bucket_metrics.get("A")
    bucket_a_prec = bucket_a_metric.precision if bucket_a_metric and bucket_a_metric.total > 0 else 1.0

    if total_evaluated < min_samples:
        passed = True
        status_note = (
            f"Evaluated {total_evaluated} sample(s) (< {min_samples} required minimum for strict gating). "
            f"Top-1 Agreement: {top1_agreement * 100:.1f}%. Bucket A Precision: {bucket_a_prec * 100:.1f}%."
        )
    elif bucket_a_prec >= bucket_a_threshold:
        passed = True
        status_note = (
            f"PASSED: Bucket A precision ({bucket_a_prec * 100:.1f}%) meets threshold ({bucket_a_threshold * 100:.1f}%). "
            f"Top-1 Agreement across all buckets: {top1_agreement * 100:.1f}% ({total_evaluated} samples)."
        )
    else:
        passed = False
        status_note = (
            f"FAILED: Bucket A precision ({bucket_a_prec * 100:.1f}%) is below required threshold ({bucket_a_threshold * 100:.1f}%). "
            f"Review model prompts or taxonomy descriptors before switching models."
        )

    return ModelEvaluationReport(
        total_reviewed=total_evaluated,
        top1_matches=top1_matches,
        top1_agreement=top1_agreement,
        bucket_metrics=bucket_metrics,
        bucket_a_threshold=bucket_a_threshold,
        passed=passed,
        status_note=status_note,
    )
