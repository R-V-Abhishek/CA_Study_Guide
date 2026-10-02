"""High-level query and analysis services for L5 Intelligence and L6 Serving."""

from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Progress, Settings
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


def get_current_score_run(session: Session, target_attempt_id: str | None = None) -> ScoreRun | None:
    """Retrieve a successful run; explicit targets never fall back across attempts."""
    if target_attempt_id is not None:
        return session.query(ScoreRun).where(
            ScoreRun.target_attempt_id == target_attempt_id,
            ScoreRun.status == "ok", ScoreRun.shadow.is_(False),
        ).order_by(ScoreRun.id.desc()).first()
    run = session.query(ScoreRun).where(
        ScoreRun.is_current.is_(True), ScoreRun.status == "ok", ScoreRun.shadow.is_(False)
    ).first()
    if not run:
        run = session.query(ScoreRun).where(
            ScoreRun.status == "ok", ScoreRun.shadow.is_(False)
        ).order_by(ScoreRun.id.desc()).first()
    return run


def get_account_settings(session: Session, user_id: int) -> Settings:
    settings = session.get(Settings, user_id)
    if settings is None:
        raise ValueError(f"Profile settings missing for account {user_id}")
    return settings


def selected_papers(session: Session, user_id: int) -> list[str]:
    settings = get_account_settings(session, user_id)
    if settings.selected_paper_ids is not None:
        return settings.selected_paper_ids
    return list(session.scalars(sa.select(Paper.id).where(Paper.is_current.is_(True))))


def get_account_score_run(session: Session, user_id: int) -> ScoreRun | None:
    settings = get_account_settings(session, user_id)
    if settings.target_attempt_id is None:
        return None
    return get_current_score_run(session, settings.target_attempt_id)


def get_subtopic_scores_for_paper(
    session: Session, paper_id: str, run_id: int | None = None, *, target_attempt_id: str | None = None
) -> dict[str, SubtopicScore]:
    """Retrieve all SubtopicScore records for a paper under the current or specified run."""
    if run_id is None:
        current_run = get_current_score_run(session, target_attempt_id)
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
    user_id: int,
    limit: int = 10,
    paper_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top weak-coverage subtopics for the student.
    
    Ordered by importance descending.
    """
    config = load_scoring_config()
    current_run = get_account_score_run(session, user_id)
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
            Node.paper_id.in_(selected_papers(session, user_id)),
            SubtopicScore.applicable.is_(True),
            SubtopicScore.freq_hits >= config.weak_flag_min_hits,
            SubtopicScore.freq_window >= config.freq_window_attempts,
            sa.or_(Progress.status == "not_started", Progress.status.is_(None)),
        )
    )

    if paper_id:
        query = query.where(Node.paper_id == paper_id)

    query = query.order_by(SubtopicScore.importance.desc(), Node.id).limit(limit)
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
    session: Session, user_id: int
) -> dict[str, Any]:
    """Compute weighted syllabus coverage per paper, group, and overall using weightage priors W(s):
    cov(paper) = Σ_{s done, applicable} W(s) / Σ_{s applicable} W(s)
    """
    current_run = get_account_score_run(session, user_id)
    if not current_run:
        return {
            "overall_coverage_pct": None, "overall_in_progress_pct": None,
            "groups": {}, "papers": {},
        }

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
            Node.paper_id.in_(selected_papers(session, user_id)),
            SubtopicScore.applicable.is_(True),
            Paper.is_current.is_(True),
            Node.status == "active",
            Node.level == "subtopic",
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

    def coverage_percentage(completed_weight: float, total_weight: float) -> float | None:
        return round(completed_weight / total_weight * 100.0, 1) if total_weight > 0 else None

    paper_results = {}
    for p_id, d in paper_accum.items():
        tot = d["total_w"]
        paper_results[p_id] = {
            "code": d["paper_code"],
            "coverage_pct": coverage_percentage(d["done_w"], tot),
            "in_progress_pct": coverage_percentage(d["in_prog_w"], tot),
        }

    group_results = {}
    for g_no, d in group_accum.items():
        tot = d["total_w"]
        group_results[g_no] = {
            "coverage_pct": coverage_percentage(d["done_w"], tot),
            "in_progress_pct": coverage_percentage(d["in_prog_w"], tot),
        }

    return {
        "overall_coverage_pct": coverage_percentage(overall_done_w, overall_total_w),
        "overall_in_progress_pct": coverage_percentage(overall_in_prog_w, overall_total_w),
        "groups": group_results,
        "papers": paper_results,
    }
