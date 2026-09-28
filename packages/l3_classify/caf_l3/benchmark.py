"""Stratified calibration test set generator and benchmark evaluation engine."""

from dataclasses import dataclass
import random
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.ref import Node

BENCHMARK_FLAG = "calibration_benchmark"
ALL_PAPERS = ["s2023.P1", "s2023.P2", "s2023.P3", "s2023.P4", "s2023.P5", "s2023.P6"]


def generate_calibration_benchmark(session: Session, size_per_paper: int = 10, seed: int = 42) -> int:
    """Sample a balanced, representative subset across all 6 papers and tag with calibration_benchmark."""
    rng = random.Random(seed)
    total_flagged = 0

    # First, clear existing benchmark flags to allow clean regeneration
    all_units = session.query(Unit).filter(Unit.current.is_(True)).all()
    for u in all_units:
        if BENCHMARK_FLAG in (u.validation_flags or []):
            flags = list(u.validation_flags)
            flags.remove(BENCHMARK_FLAG)
            u.validation_flags = flags

    session.flush()

    for paper_id in ALL_PAPERS:
        # Fetch confirmed documents for this paper
        units_with_doc = (
            session.query(Unit, Document)
            .join(Document, Unit.document_id == Document.id)
            .filter(
                Document.paper_id == paper_id,
                Unit.current.is_(True),
                Unit.is_gradable.is_(True),
            )
            .all()
        )

        if not units_with_doc:
            continue

        # Group by document to ensure temporal/attempt diversity
        units_by_doc: dict[int, list[Unit]] = {}
        for unit, doc in units_with_doc:
            units_by_doc.setdefault(doc.id, []).append(unit)

        selected_for_paper: list[Unit] = []
        doc_ids = list(units_by_doc.keys())
        rng.shuffle(doc_ids)

        # Round-robin selection across available documents
        idx = 0
        while len(selected_for_paper) < size_per_paper and any(units_by_doc.values()):
            d_id = doc_ids[idx % len(doc_ids)]
            if units_by_doc[d_id]:
                # Pick a unit with marks diversity
                u = units_by_doc[d_id].pop(0)
                selected_for_paper.append(u)
            idx += 1

        for u in selected_for_paper:
            flags = list(u.validation_flags or [])
            if BENCHMARK_FLAG not in flags:
                flags.append(BENCHMARK_FLAG)
                u.validation_flags = flags
                total_flagged += 1

    session.commit()
    return total_flagged


def list_benchmark_units(session: Session) -> list[dict[str, Any]]:
    """List all units currently designated as the calibration benchmark."""
    units_with_doc = (
        session.query(Unit, Document)
        .join(Document, Unit.document_id == Document.id)
        .filter(
            Unit.current.is_(True),
            Unit.is_gradable.is_(True),
        )
        .order_by(Document.paper_id.asc(), Unit.id.asc())
        .all()
    )

    results = []
    for u, doc in units_with_doc:
        if BENCHMARK_FLAG in (u.validation_flags or []):
            results.append({
                "unit_id": u.id,
                "paper_id": doc.paper_id,
                "attempt_id": doc.attempt_id,
                "display_label": u.display_label,
                "marks": u.marks,
                "classify_status": u.classify_status,
                "question_preview": (u.question_text or "")[:120].strip(),
            })

    return results


@dataclass
class BenchmarkPaperMetric:
    paper_id: str
    total: int
    decided: int
    matched: int
    precision: float
    status: str


@dataclass
class BenchmarkEvaluationReport:
    total_samples: int
    total_decided: int
    top1_matches: int
    overall_precision: float
    passed: bool
    paper_metrics: dict[str, BenchmarkPaperMetric]
    status_note: str


def evaluate_calibration_benchmark(session: Session, threshold: float = 0.80) -> BenchmarkEvaluationReport:
    """Evaluate human decisions vs AI suggestions specifically on the benchmark subset."""
    benchmark_units = (
        session.query(Unit, Document)
        .join(Document, Unit.document_id == Document.id)
        .filter(Unit.current.is_(True))
        .all()
    )
    b_units = [(u, doc) for u, doc in benchmark_units if BENCHMARK_FLAG in (u.validation_flags or [])]
    total_samples = len(b_units)

    if total_samples == 0:
        return BenchmarkEvaluationReport(
            total_samples=0,
            total_decided=0,
            top1_matches=0,
            overall_precision=0.0,
            passed=False,
            paper_metrics={},
            status_note="No benchmark units found. Run 'caf classify test-set --generate' first.",
        )

    b_unit_ids = [u.id for u, _ in b_units]
    b_fingerprints = [u.fingerprint for u, _ in b_units]

    # Fetch latest human decisions
    decisions = (
        session.query(Decision)
        .filter(Decision.unit_fingerprint.in_(b_fingerprints))
        .order_by(Decision.id.desc())
        .all()
    )
    decisions_by_fp = {d.unit_fingerprint: d for d in decisions}

    # Fetch latest primary tag suggestions
    suggestions = (
        session.query(TagSuggestion)
        .filter(
            TagSuggestion.unit_id.in_(b_unit_ids),
            TagSuggestion.role == "primary",
        )
        .order_by(TagSuggestion.id.desc())
        .all()
    )
    sugg_by_unit = {s.unit_id: s for s in suggestions}

    paper_stats: dict[str, dict[str, int]] = {
        p: {"total": 0, "decided": 0, "matched": 0} for p in ALL_PAPERS
    }

    total_decided = 0
    top1_matches = 0

    for u, doc in b_units:
        p_id = doc.paper_id or "unknown"
        if p_id in paper_stats:
            paper_stats[p_id]["total"] += 1

        dec = decisions_by_fp.get(u.fingerprint)
        sugg = sugg_by_unit.get(u.id)

        if dec and sugg:
            curator_primary = dec.payload.get("primary_node_id")
            if curator_primary:
                total_decided += 1
                if p_id in paper_stats:
                    paper_stats[p_id]["decided"] += 1

                if sugg.node_id == curator_primary:
                    top1_matches += 1
                    if p_id in paper_stats:
                        paper_stats[p_id]["matched"] += 1

    overall_prec = round(top1_matches / total_decided, 4) if total_decided > 0 else 0.0
    passed = (total_decided >= 20) and (overall_prec >= threshold)

    paper_metrics: dict[str, BenchmarkPaperMetric] = {}
    for p_id, stats in paper_stats.items():
        t = stats["total"]
        d = stats["decided"]
        m = stats["matched"]
        prec = round(m / d, 4) if d > 0 else 0.0
        status = "PASSED" if prec >= threshold and d > 0 else ("PENDING" if d == 0 else "FAIL")
        paper_metrics[p_id] = BenchmarkPaperMetric(
            paper_id=p_id,
            total=t,
            decided=d,
            matched=m,
            precision=prec,
            status=status,
        )

    if total_decided < 20:
        status_note = (
            f"Evaluated {total_decided}/{total_samples} benchmark decisions (minimum 20 recommended for gating). "
            f"Current Precision: {overall_prec * 100:.1f}%."
        )
    elif passed:
        status_note = (
            f"PASSED: Benchmark precision ({overall_prec * 100:.1f}%) meets quality gate threshold ({threshold * 100:.1f}%). "
            f"Safe to bulk-accept remaining Bucket A units."
        )
    else:
        status_note = (
            f"FAILED: Benchmark precision ({overall_prec * 100:.1f}%) is below {threshold * 100:.1f}%. "
            f"Review model prompts before bulk-accepting."
        )

    return BenchmarkEvaluationReport(
        total_samples=total_samples,
        total_decided=total_decided,
        top1_matches=top1_matches,
        overall_precision=overall_prec,
        passed=passed,
        paper_metrics=paper_metrics,
        status_note=status_note,
    )
