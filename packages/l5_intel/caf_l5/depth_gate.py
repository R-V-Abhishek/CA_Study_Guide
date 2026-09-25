"""L5 Depth Gate Engine: evaluates marginal exam intelligence value of historical bands."""

import logging
from pathlib import Path
import statistics
import tomllib
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.intel import DepthGateReport, ScoreRun, SubtopicScore
from caf_db.models.ref import DocType, Node, Paper
from caf_l4.publish import compute_law_stale
from caf_l5.scoring import recompute_scores

logger = logging.getLogger(__name__)


def compute_ranks(values: list[float], reverse: bool = True) -> list[float]:
    """Compute 1-based fractional ranks (higher value = rank 1 if reverse=True)."""
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(enumerate(values), key=lambda x: x[1], reverse=reverse)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            orig_idx = indexed[k][0]
            ranks[orig_idx] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_correlation(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation between two vectors x and y."""
    n = len(x)
    if n <= 1:
        return 1.0
    rank_x = compute_ranks(x, reverse=True)
    rank_y = compute_ranks(y, reverse=True)
    mean_x = sum(rank_x) / n
    mean_y = sum(rank_y) / n
    num = sum((rx - mean_x) * (ry - mean_y) for rx, ry in zip(rank_x, rank_y))
    den_x = sum((rx - mean_x) ** 2 for rx in rank_x)
    den_y = sum((ry - mean_y) ** 2 for ry in rank_y)
    den = (den_x * den_y) ** 0.5
    if den == 0:
        return 1.0 if x == y else 0.0
    return round(float(num / den), 4)


def load_depth_config(config_path: Path | str = "config/depth.toml") -> dict[str, Any]:
    """Load depth configuration from TOML file."""
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def compute_depth_gate(
    session: Session,
    paper: str,
    band: str,
    top_k: int = 50,
    record_report: bool = True,
    config_path: Path | str = "config/depth.toml",
) -> DepthGateReport:
    """Compute Depth Gate metrics comparing current baseline vs shadow run with the band's provisional appearances.
    
    Args:
        session: SQLAlchemy DB session
        paper: Paper code (e.g. 'P1') or ID (e.g. 's2023.P1')
        band: Historical band (e.g. 's2017:2019')
        top_k: Top K subtopics to evaluate for Jaccard and Spearman (default 50)
        record_report: If True, persist DepthGateReport row in database
        config_path: Path to depth.toml
        
    Returns:
        The generated DepthGateReport
    """
    # 1. Resolve paper
    target_paper = (
        session.query(Paper)
        .filter((Paper.code == paper) | (Paper.id == paper))
        .filter(Paper.is_current.is_(True))
        .first()
    )
    if not target_paper:
        target_paper = (
            session.query(Paper)
            .filter((Paper.code == paper) | (Paper.id == paper))
            .first()
        )
    if not target_paper:
        raise ValueError(f"Paper '{paper}' not found")

    paper_id = target_paper.id
    paper_code = target_paper.code

    # 2. Get baseline score run
    baseline_run = (
        session.query(ScoreRun)
        .filter(
            ScoreRun.is_current.is_(True),
            ScoreRun.shadow.is_(False),
            ScoreRun.status == "ok",
        )
        .first()
    )
    if not baseline_run:
        logger.info("No current baseline score run found. Triggering recompute.")
        baseline_run = recompute_scores(session, shadow=False)

    # 3. Find gradable units in band
    units_query = (
        session.query(Unit)
        .join(Document, Document.id == Unit.document_id)
        .filter(
            Document.depth_band == band,
            (Document.paper_id == paper_id) | (Document.paper_id.endswith(f".{paper_code}")),
            Unit.is_gradable.is_(True),
            Unit.current.is_(True),
        )
    )
    units_to_review = units_query.count()

    # 4. Find shadow tag suggestions in bucket A and B for units in band
    suggestions = (
        session.query(TagSuggestion, Unit, Document)
        .join(Unit, Unit.id == TagSuggestion.unit_id)
        .join(Document, Document.id == Unit.document_id)
        .filter(
            Document.depth_band == band,
            (Document.paper_id == paper_id) | (Document.paper_id.endswith(f".{paper_code}")),
            TagSuggestion.role == "primary",
            TagSuggestion.bucket.in_(["A", "B"]),
            Unit.is_gradable.is_(True),
            Unit.current.is_(True),
        )
        .order_by(TagSuggestion.id.asc())
        .all()
    )

    # Deduplicate by unit (keep latest suggestion)
    unit_suggestions: dict[int, tuple[TagSuggestion, Unit, Document]] = {}
    for sugg, u, d in suggestions:
        unit_suggestions[u.id] = (sugg, u, d)

    # Build provisional appearances
    doc_types = {dt.id: dt for dt in session.query(DocType).all()}
    provisional_items: list[tuple[Appearance, AppearanceTag]] = []
    for sugg, u, d in unit_suggestions.values():
        doc_type = doc_types.get(d.doc_type_id) if d.doc_type_id else None
        signal_class = doc_type.signal_class if doc_type else "exam"
        law_stale = compute_law_stale(
            session, d.attempt_id or "2024-05", d.paper_id or paper_id, [sugg.node_id]
        )
        p_app = Appearance(
            unit_fingerprint=u.fingerprint,
            source_unit_id=u.id,
            doc_sha256=d.sha256,
            attempt_id=d.attempt_id or "2024-05",
            source_paper_id=d.paper_id or paper_id,
            doc_type_id=d.doc_type_id or "suggested_answer",
            signal_class=signal_class,
            series=d.series,
            display_label=u.display_label,
            marks=u.marks or 0,
            gist=u.display_label,
            page_start=u.page_start,
            page_end=u.page_end,
            law_stale=law_stale,
            status="published",
        )
        p_tag = AppearanceTag(
            node_id=sugg.node_id,
            share=1.0,
        )
        provisional_items.append((p_app, p_tag))

    # 5. Run shadow scoring
    shadow_run = recompute_scores(
        session,
        target_attempt_id=baseline_run.target_attempt_id,
        shadow=True,
        provisional_items=provisional_items,
    )

    # 6. Load baseline & shadow subtopic scores for this paper
    base_scores_list = (
        session.query(SubtopicScore)
        .join(Node, Node.id == SubtopicScore.node_id)
        .filter(
            SubtopicScore.score_run_id == baseline_run.id,
            Node.paper_id == paper_id,
            SubtopicScore.applicable.is_(True),
        )
        .all()
    )
    shadow_scores_list = (
        session.query(SubtopicScore)
        .join(Node, Node.id == SubtopicScore.node_id)
        .filter(
            SubtopicScore.score_run_id == shadow_run.id,
            Node.paper_id == paper_id,
            SubtopicScore.applicable.is_(True),
        )
        .all()
    )

    base_map = {s.node_id: s for s in base_scores_list}
    shadow_map = {s.node_id: s for s in shadow_scores_list}

    effective_k = min(top_k, len(base_map)) if base_map else 0

    if effective_k > 0:
        top_base = sorted(
            base_scores_list, key=lambda s: (s.importance, s.node_id), reverse=True
        )[:effective_k]
        top_shadow = sorted(
            shadow_scores_list, key=lambda s: (s.importance, s.node_id), reverse=True
        )[:effective_k]

        base_top_ids = {s.node_id for s in top_base}
        shadow_top_ids = {s.node_id for s in top_shadow}

        inter = base_top_ids & shadow_top_ids
        union = base_top_ids | shadow_top_ids

        jaccard = round(len(inter) / len(union), 4) if union else 1.0

        union_sorted = sorted(list(union))
        base_vals = [base_map[nid].importance if nid in base_map else 0.0 for nid in union_sorted]
        shadow_vals = [shadow_map[nid].importance if nid in shadow_map else 0.0 for nid in union_sorted]
        spearman = compute_spearman_correlation(base_vals, shadow_vals)
    else:
        jaccard = 1.0
        spearman = 1.0

    # 7. Newly asked nodes: subtopics with 0 exam history in baseline and > 0 in shadow
    newly_asked_nodes = 0
    for nid, s in shadow_map.items():
        base_s = base_map.get(nid)
        base_exams = (base_s.exam_count if base_s else 0) or 0
        if base_exams == 0 and (s.exam_count or 0) > 0:
            newly_asked_nodes += 1

    # 8. Review hours estimation
    recent_decisions = (
        session.query(Decision.seconds_spent)
        .filter(Decision.seconds_spent.isnot(None), Decision.seconds_spent > 0)
        .order_by(Decision.id.desc())
        .limit(500)
        .all()
    )
    times = [float(r[0]) for r in recent_decisions if r[0] is not None]
    if len(times) >= 5:
        med_seconds = float(statistics.median(times))
    else:
        med_seconds = 45.0

    est_review_hours = round((units_to_review * med_seconds) / 3600.0, 2)

    # 9. Recommendation logic
    depth_cfg = load_depth_config(config_path)
    paper_cfg = depth_cfg.get("paper", {}).get(paper_code, {})
    practice_value = paper_cfg.get("practice_value", False)

    if jaccard < 0.9 or newly_asked_nodes >= 10:
        decision = "continue"
        note = (
            f"Jaccard ({jaccard:.4f}) < 0.9 or newly asked nodes ({newly_asked_nodes}) >= 10: "
            f"band adds significant exam signal"
        )
    elif practice_value:
        decision = "continue_practice_value"
        note = (
            f"Stability high (Jaccard {jaccard:.4f} >= 0.9, new nodes {newly_asked_nodes} < 10), "
            f"but practice_value=true in depth.toml: recommended for practice questions"
        )
    else:
        decision = "stop"
        note = (
            f"Stability reached (Jaccard {jaccard:.4f} >= 0.9, new nodes {newly_asked_nodes} < 10) "
            f"and practice_value is false: marginal exam value is low"
        )

    # 10. Construct DepthGateReport
    report = DepthGateReport(
        paper_code=paper_code,
        band=band,
        baseline_run_id=baseline_run.id,
        shadow_run_id=shadow_run.id,
        top_k=effective_k,
        jaccard=jaccard,
        spearman=spearman,
        newly_asked_nodes=newly_asked_nodes,
        units_to_review=units_to_review,
        est_review_hours=est_review_hours,
        decision=decision,
        decided_note=note,
    )

    if record_report:
        session.add(report)
        session.commit()

    return report


def get_depth_gate_reports(
    session: Session,
    paper: str | None = None,
    band: str | None = None,
) -> list[DepthGateReport]:
    """Retrieve historical depth gate reports."""
    query = session.query(DepthGateReport)
    if paper:
        paper_code = paper.split(".")[-1]
        query = query.filter((DepthGateReport.paper_code == paper_code) | (DepthGateReport.paper_code == paper))
    if band:
        query = query.filter(DepthGateReport.band == band)
    return query.order_by(DepthGateReport.id.desc()).all()
