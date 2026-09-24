"""High-level query and analysis services for L5 Intelligence and L6 Serving."""

from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Progress
from caf_db.models.intel import IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ref import Node, Paper
from caf_l5.config import ScoringConfig, load_scoring_config


def is_subtopic_weak(
    applicable: bool,
    freq_hits: int,
    freq_window: int,
    status: str,
    config: ScoringConfig | None = None,
) -> bool:
    """Evaluate the weak-coverage flag for a subtopic:
    weak(s) = applicable(s,T) ∧ F(s) ≥ weak_flag_min_hits ∧ freq_window ≥ N ∧ status(s) = not_started
    """
    if config is None:
        config = load_scoring_config()

    return (
        applicable
        and freq_hits >= config.weak_flag_min_hits
        and freq_window >= config.freq_window_attempts
        and status == "not_started"
    )


def get_current_score_run(session: Session) -> ScoreRun | None:
    """Retrieve the active current ScoreRun."""
    run = session.query(ScoreRun).where(
        ScoreRun.is_current.is_(True), ScoreRun.status == "ok"
    ).first()
    if not run:
        run = session.query(ScoreRun).where(
            ScoreRun.status == "ok"
        ).order_by(ScoreRun.id.desc()).first()
    return run


def get_subtopic_scores_for_paper(
    session: Session, paper_id: str, run_id: int | None = None
) -> dict[str, SubtopicScore]:
    """Retrieve all SubtopicScore records for a paper under the current or specified run."""
    if run_id is None:
        current_run = get_current_score_run(session)
        if not current_run:
            return {}
        run_id = current_run.id

    rows = (
        session.query(SubtopicScore)
        .join(Node, Node.id == SubtopicScore.node_id)
        .where(
            SubtopicScore.score_run_id == run_id,
            Node.paper_id == paper_id,
        )
        .all()
    )
    return {row.node_id: row for row in rows}


def get_weak_subtopics(
    session: Session,
    user_id: int = 1,
    limit: int = 10,
    paper_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top weak-coverage subtopics for the student.
    
    Ordered by importance descending.
    """
    config = load_scoring_config()
    current_run = get_current_score_run(session)
    if not current_run:
        return []

    query = (
        session.query(SubtopicScore, Node, Paper, Progress)
        .join(Node, Node.id == SubtopicScore.node_id)
        .join(Paper, Paper.id == Node.paper_id)
        .outerjoin(
            Progress,
            sa.and_(Progress.node_id == Node.id, Progress.user_id == user_id),
        )
        .where(
            SubtopicScore.score_run_id == current_run.id,
            SubtopicScore.applicable.is_(True),
            SubtopicScore.freq_hits >= config.weak_flag_min_hits,
            SubtopicScore.freq_window >= config.freq_window_attempts,
            sa.or_(Progress.status == "not_started", Progress.status.is_(None)),
        )
    )

    if paper_id:
        query = query.where(Node.paper_id == paper_id)

    query = query.order_by(SubtopicScore.importance.desc()).limit(limit)
    results = query.all()

    items = []
    for score, node, paper, prog in results:
        status = prog.status if prog else "not_started"
        items.append({
            "node_id": node.id,
            "node_name": node.name,
            "paper_id": paper.id,
            "paper_code": paper.code,
            "importance": score.importance,
            "freq_hits": score.freq_hits,
            "freq_window": score.freq_window,
            "exam_marks_total": score.exam_marks_total,
            "exam_count": score.exam_count,
            "status": status,
        })
    return items


def get_ingestion_coverage_matrix(
    session: Session, run_id: int | None = None
) -> dict[str, Any]:
    """Retrieve the paper x attempt ingestion coverage matrix."""
    if run_id is None:
        current_run = get_current_score_run(session)
        if not current_run:
            return {"run_id": None, "coverage": []}
        run_id = current_run.id

    rows = (
        session.query(IngestionCoverage)
        .where(IngestionCoverage.score_run_id == run_id)
        .all()
    )

    matrix = []
    for r in rows:
        matrix.append({
            "paper_id": r.paper_id,
            "attempt_id": r.attempt_id,
            "exam_published": r.exam_published,
            "practice_published": r.practice_published,
        })

    return {
        "run_id": run_id,
        "coverage": matrix,
    }


def compute_weighted_coverage(
    session: Session, user_id: int = 1
) -> dict[str, Any]:
    """Compute weighted syllabus coverage per paper, group, and overall using weightage priors W(s):
    cov(paper) = Σ_{s done, applicable} W(s) / Σ_{s applicable} W(s)
    """
    current_run = get_current_score_run(session)
    if not current_run:
        return {"overall": 0.0, "groups": {}, "papers": {}}

    scores_and_nodes = (
        session.query(SubtopicScore, Node, Paper, Progress)
        .join(Node, Node.id == SubtopicScore.node_id)
        .join(Paper, Paper.id == Node.paper_id)
        .outerjoin(
            Progress,
            sa.and_(Progress.node_id == Node.id, Progress.user_id == user_id),
        )
        .where(
            SubtopicScore.score_run_id == current_run.id,
            SubtopicScore.applicable.is_(True),
            Paper.is_current.is_(True),
        )
        .all()
    )

    paper_accum: dict[str, dict[str, float]] = {}
    group_accum: dict[int, dict[str, float]] = {1: {"total_w": 0.0, "done_w": 0.0, "in_prog_w": 0.0},
                                                2: {"total_w": 0.0, "done_w": 0.0, "in_prog_w": 0.0}}
    overall_total_w = 0.0
    overall_done_w = 0.0
    overall_in_prog_w = 0.0

    for score, node, paper, prog in scores_and_nodes:
        p_id = paper.id
        g_no = paper.group_no or 1
        w = score.weight_prior
        status = prog.status if prog else "not_started"

        if p_id not in paper_accum:
            paper_accum[p_id] = {
                "paper_code": paper.code,
                "total_w": 0.0,
                "done_w": 0.0,
                "in_prog_w": 0.0,
            }

        paper_accum[p_id]["total_w"] += w
        group_accum[g_no]["total_w"] += w
        overall_total_w += w

        if status == "done":
            paper_accum[p_id]["done_w"] += w
            group_accum[g_no]["done_w"] += w
            overall_done_w += w
        elif status == "in_progress":
            paper_accum[p_id]["in_prog_w"] += w
            group_accum[g_no]["in_prog_w"] += w
            overall_in_prog_w += w

    paper_results = {}
    for p_id, d in paper_accum.items():
        tot = d["total_w"]
        cov = (d["done_w"] / tot * 100.0) if tot > 0 else 0.0
        in_p = (d["in_prog_w"] / tot * 100.0) if tot > 0 else 0.0
        paper_results[p_id] = {
            "code": d["paper_code"],
            "coverage_pct": round(cov, 1),
            "in_progress_pct": round(in_p, 1),
        }

    group_results = {}
    for g_no, d in group_accum.items():
        tot = d["total_w"]
        cov = (d["done_w"] / tot * 100.0) if tot > 0 else 0.0
        in_p = (d["in_prog_w"] / tot * 100.0) if tot > 0 else 0.0
        group_results[g_no] = {
            "coverage_pct": round(cov, 1),
            "in_progress_pct": round(in_p, 1),
        }

    overall_cov = (overall_done_w / overall_total_w * 100.0) if overall_total_w > 0 else 0.0
    overall_in_p = (overall_in_prog_w / overall_total_w * 100.0) if overall_total_w > 0 else 0.0

    return {
        "overall_coverage_pct": round(overall_cov, 1),
        "overall_in_progress_pct": round(overall_in_p, 1),
        "groups": group_results,
        "papers": paper_results,
    }
