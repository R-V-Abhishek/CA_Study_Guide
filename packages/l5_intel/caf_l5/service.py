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


def get_current_score_run(session: Session, target_attempt_id: str | None = None,
                          taxonomy_version_id: int | None = None,
                          config_hash: str | None = None) -> ScoreRun | None:
    if taxonomy_version_id is None:
        from caf_l5.context import approved_binding
        from caf_db.models.taxonomy import TaxonomyRelease
        binding = approved_binding(session, target_attempt_id) if target_attempt_id else None
        if binding:
            taxonomy_version_id = binding.taxonomy_version_id
            if config_hash is None:
                configured = ScoringConfig.model_validate(binding.scoring_config) if binding.scoring_config else load_scoring_config()
                config_hash = configured.config_hash
        elif session.scalar(sa.select(TaxonomyRelease.taxonomy_version_id).where(
                TaxonomyRelease.status != "legacy").limit(1)) is not None:
            return None
    query = session.query(ScoreRun).where(ScoreRun.status == "ok", ScoreRun.shadow.is_(False),
        ScoreRun.taxonomy_version_id == taxonomy_version_id, ScoreRun.is_current.is_(True))
    if target_attempt_id is not None:
        query = query.where(ScoreRun.target_attempt_id == target_attempt_id)
    if config_hash is not None:
        query = query.where(ScoreRun.config_hash == config_hash)
    return query.order_by(ScoreRun.corpus_generation.desc(), ScoreRun.id.desc()).first()


def get_account_settings(session: Session, user_id: int) -> Settings:
    settings = session.get(Settings, user_id)
    if settings is None:
        raise ValueError(f"Profile settings missing for account {user_id}")
    return settings


def selected_papers(session: Session, user_id: int) -> list[str]:
    settings = session.get(Settings, user_id)
    if settings is None:
        return []
    if settings.selected_paper_ids is not None:
        return settings.selected_paper_ids
    return list(session.scalars(sa.select(Paper.id).where(Paper.is_current.is_(True))))


def get_account_score_run(session: Session, user_id: int) -> ScoreRun | None:
    from caf_l5.context import resolve_context
    return resolve_context(session, user_id).run


def get_subtopic_scores_for_paper(
    session: Session, paper_id: str, run_id: int | None = None, *, target_attempt_id: str | None = None, taxonomy_version_id: int | None = None
) -> dict[str, SubtopicScore]:
    """Retrieve all SubtopicScore records for a paper under the current or specified run."""
    if run_id is None:
        current_run = get_current_score_run(session, target_attempt_id, taxonomy_version_id)
        if not current_run:
            return {}
        run_id = current_run.id
    else:
        run = session.get(ScoreRun, run_id)
        if run is None or run.taxonomy_version_id != taxonomy_version_id or (
            target_attempt_id is not None and run.target_attempt_id != target_attempt_id
        ):
            return {}

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
    from caf_l5.context import resolve_context
    context = resolve_context(session, user_id)
    current_run = context.run
    config = ScoringConfig.model_validate(current_run.config_snapshot) if current_run and current_run.config_snapshot else context.config
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
            SubtopicScore.importance.is_not(None),
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

    run = session.get(ScoreRun, run_id)
    evidence = run.input_manifest.get("coverage", []) if run and run.input_manifest else []
    if evidence:
        matrix = [{"paper_id": item["paper_id"], "attempt_id": item["attempt_id"],
            "source_family": item["source_family"], "exam_published": bool(item["eligible"]),
            "practice_published": False, "usable_exam": bool(item["eligible"] and item["source_family"] in
                {"QP", "question_paper", "exam", "past_exam"}),
            "inventory_reviewed": item["inventory_reviewed"], "expected_sources": item["expected_slots"],
            "acquired_sources": item["acquired_count"], "reviewed_roots": item["reviewed_roots"],
            "reviewed_parts": item["reviewed_parts"], "blockers": item["exclusions"]} for item in evidence]
    else:
        matrix = [{"paper_id": row.paper_id, "attempt_id": row.attempt_id,
                   "exam_published": row.exam_published, "practice_published": row.practice_published}
                  for row in rows]

    return {
        "run_id": run_id,
        "coverage": matrix,
    }


def compute_weighted_coverage(session: Session, user_id: int) -> dict[str, Any]:
    """Personal syllabus progress; absent reviewed priors means unweighted counts."""
    from caf_l5.context import resolve_context, context_nodes, context_leaf_ids
    context = resolve_context(session, user_id)
    nodes = context_nodes(session, context)
    terminal_ids = context_leaf_ids(session, context)
    allowed = set(selected_papers(session, user_id))
    leaves = [node for node in nodes if node.id in terminal_ids and node.paper_id in allowed]
    scores = {row.node_id: row for row in session.scalars(sa.select(SubtopicScore).where(
        SubtopicScore.score_run_id == context.run.id))} if context.run else {}
    weighted = bool(leaves) and all(node.id in scores and scores[node.id].weight_prior is not None
                                  for node in leaves)
    if context.taxonomy_version_id is not None:
        weighted = weighted and all(scores[node.id].evidence.get("components", {}).get(
            "prior", {}).get("available", False) for node in leaves)
    progress = {row.node_id: row.status for row in session.scalars(sa.select(Progress).where(
        Progress.user_id == user_id))}
    papers = {row.id: row for row in session.scalars(sa.select(Paper))}
    totals: dict[str, list[float]] = {}
    groups: dict[int, list[float]] = {}
    overall = [0.0, 0.0, 0.0]
    for node in leaves:
        weight = scores[node.id].weight_prior if weighted else 1.0
        status = progress.get(node.id, "not_started")
        values = [weight, weight if status == "done" else 0.0,
                  weight if status == "in_progress" else 0.0]
        paper = papers[node.paper_id]
        for aggregate in (totals.setdefault(paper.id, [0.0, 0.0, 0.0]),
                          groups.setdefault(paper.group_no or 1, [0.0, 0.0, 0.0]), overall):
            for index, value in enumerate(values):
                aggregate[index] += value
    def percentages(values):
        return {"coverage_pct": round(values[1] / values[0] * 100, 1) if values[0] else None,
                "in_progress_pct": round(values[2] / values[0] * 100, 1) if values[0] else None}
    summary = percentages(overall)
    return {"basis": "weighted" if weighted else ("unweighted" if leaves else "unavailable"),
            "overall_coverage_pct": summary["coverage_pct"],
            "overall_in_progress_pct": summary["in_progress_pct"],
            "papers": {paper_id: {"code": papers[paper_id].code, **percentages(values)}
                       for paper_id, values in totals.items()},
            "groups": {group: percentages(values) for group, values in groups.items()},
            "context": context.identity, "freshness": context.freshness}
