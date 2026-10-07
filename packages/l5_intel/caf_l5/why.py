"""Explainability (Why Payload) generator for L5 Intelligence."""

from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.intel import IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ref import Attempt, Node, Paper, WeightageMember, WeightageSection
from caf_l5.config import ScoringConfig, load_scoring_config
from caf_l5.scoring import calculate_attributed_marks, compute_age_months, compute_decay
from caf_l5.service import get_current_score_run


def get_legacy_subtopic_why(
    session: Session,
    node_id: str,
    run_id: int | None = None,
    *, target_attempt_id: str | None = None,
) -> dict[str, Any]:
    """Generate detailed explainability breakdown for a subtopic score.
    
    Returns all parameters, contributing appearances, intermediate decay/attributed marks,
    weightage section priors, normalization factors, and frequency calculations.
    """
    # 1. Fetch node hierarchy
    subtopic = session.get(Node, node_id)
    if not subtopic or subtopic.level != "subtopic":
        raise ValueError(f"Subtopic node not found: {node_id}")

    from caf_l0.hierarchy import ancestor_at, descendant_leaves, version_nodes
    nodes = {node.id: node for node in version_nodes(session)}
    topic = ancestor_at(node_id, nodes, "topic")
    chapter = ancestor_at(node_id, nodes, "chapter")
    paper = session.get(Paper, subtopic.paper_id) if subtopic.paper_id else None

    # 2. Fetch score run
    if run_id:
        score_run = session.get(ScoreRun, run_id)
        if score_run and (score_run.shadow or score_run.status != "ok"):
            raise ValueError("Only successful, non-shadow score runs can be explained")
        from caf_l0.releases import active_version
        release = active_version(session)
        expected_version = release.taxonomy_version_id if release else None
        if score_run and (score_run.taxonomy_version_id != expected_version or (
            target_attempt_id is not None and score_run.target_attempt_id != target_attempt_id
        )):
            raise ValueError("Only successful non-shadow runs matching the target attempt and taxonomy may be explained")
    else:
        score_run = get_current_score_run(session, target_attempt_id)

    # 3. Fetch subtopic score record
    score_rec = session.query(SubtopicScore).where(
        SubtopicScore.score_run_id == score_run.id,
        SubtopicScore.node_id == node_id,
    ).first() if score_run else None

    # Stored scores remain authoritative. Never derive a historical formula from
    # a different configuration merely because it is today's configuration.
    configuration_source = None
    config = None
    if score_run and score_run.config_snapshot is not None:
        config = ScoringConfig.model_validate(score_run.config_snapshot)
        configuration_source = "snapshot"
    elif score_run:
        current_config = load_scoring_config()
        if current_config.config_hash == score_run.config_hash:
            config = current_config
            configuration_source = "matching_current"

    identity = {
        "id": score_run.id,
        "version": score_run.scoring_version,
        "target_attempt_id": score_run.target_attempt_id,
        "taxonomy_version_id": score_run.taxonomy_version_id,
        "computed_at": score_run.finished_at.isoformat() if score_run.finished_at else None,
        "config_hash": score_run.config_hash, "corpus_generation": score_run.corpus_generation,
    } if score_run else None
    subtopic_info = {
        "id": subtopic.id,
        "name": subtopic.name,
        "paper": {"id": paper.id, "code": paper.code, "name": paper.name} if paper else None,
        "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
        "topic": {"id": topic.id, "name": topic.name} if topic else None,
        "applicable": score_rec.applicable if score_rec else True,
    }
    if not score_run or not score_rec or config is None:
        status = "no_score_run" if not score_run else (
            "score_unavailable" if not score_rec else "historical_configuration_unavailable"
        )
        messages = {
            "no_score_run": "No completed score run is available.",
            "score_unavailable": "No score is available for this subtopic in the selected run.",
            "historical_configuration_unavailable": "Historical configuration unavailable.",
        }
        return {
            "node_id": node_id, "explanation_status": status, "error": messages[status],
            "configuration_source": configuration_source, "score_run": identity,
            "subtopic": subtopic_info,
            "importance_breakdown": {
                "importance": score_rec.importance if score_rec else None,
                "weights": None, "exam": None, "practice": None, "weightage_prior": None,
            },
            "frequency": None, "weightage_section": None, "appearances": [],
        }

    # Older runs did not persist occurrence contributions. Their stored scores
    # remain explainable; today's corpus cannot recreate missing historical inputs.
    window_attempts = []
    contributing_appearances = []
    hit_attempts = set()
    w_info = None

    # 8. Paper normalization maximums
    paper_scores = session.query(SubtopicScore).join(
        Node, Node.id == SubtopicScore.node_id
    ).where(
        SubtopicScore.score_run_id == score_run.id,
        Node.paper_id == subtopic.paper_id,
        SubtopicScore.applicable.is_(True),
    ).all()

    max_e = max([s.exam_score for s in paper_scores], default=0.0)
    max_p = max([s.practice_score for s in paper_scores], default=0.0)
    max_w = max([s.weight_prior for s in paper_scores], default=0.0)

    e_val = score_rec.exam_score if score_rec else 0.0
    p_val = score_rec.practice_score if score_rec else 0.0
    w_val = score_rec.weight_prior if score_rec else 0.0

    e_norm = (e_val / max_e) if max_e > 0 else 0.0
    p_norm = (p_val / max_p) if max_p > 0 else 0.0
    w_norm = (w_val / max_w) if max_w > 0 else 0.0

    return {
        "node_id": node_id,
        "explanation_status": "available",
        "error": None,
        "configuration_source": configuration_source,
        "historical_evidence_status": "occurrence_inputs_unavailable",
        "score_run": {
            "id": score_run.id,
            "version": score_run.scoring_version,
            "target_attempt_id": score_run.target_attempt_id,
            "computed_at": score_run.finished_at.isoformat() if score_run.finished_at else None,
            "taxonomy_version_id": score_run.taxonomy_version_id,
            "config_hash": score_run.config_hash, "corpus_generation": score_run.corpus_generation,
        },
        "subtopic": {
            "id": subtopic.id,
            "name": subtopic.name,
            "paper": {"id": paper.id, "code": paper.code, "name": paper.name} if paper else None,
            "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
            "topic": {"id": topic.id, "name": topic.name} if topic else None,
            "applicable": score_rec.applicable if score_rec else True,
        },
        "importance_breakdown": {
            "importance": score_rec.importance if score_rec else 0.0,
            "weights": {
                "exam": config.weights.exam,
                "practice": config.weights.practice,
                "prior": config.weights.prior,
            },
            "exam": {
                "score_E": round(e_val, 4),
                "paper_max_E": round(max_e, 4),
                "normalized_E_hat": round(e_norm, 4),
                "normalized_E_pct": round(e_norm * 100, 2),
                "weighted_contribution": round(config.weights.exam * e_norm, 4),
                "weighted_contribution_pct": round(config.weights.exam * e_norm * 100, 2),
            },
            "practice": {
                "score_P": round(p_val, 4),
                "paper_max_P": round(max_p, 4),
                "normalized_P_hat": round(p_norm, 4),
                "normalized_P_pct": round(p_norm * 100, 2),
                "weighted_contribution": round(config.weights.practice * p_norm, 4),
                "weighted_contribution_pct": round(config.weights.practice * p_norm * 100, 2),
            },
            "weightage_prior": {
                "available": score_run.taxonomy_version_id is None,
                "unavailable_reason": "Applicable official weightage mappings are unavailable for this textbook taxonomy. Prior contribution is zero; configured weights are unchanged." if score_run.taxonomy_version_id is not None else None,
                "weight_prior_W": round(w_val, 4),
                "paper_max_W": round(max_w, 4),
                "normalized_W_hat": round(w_norm, 4),
                "normalized_W_pct": round(w_norm * 100, 2),
                "weighted_contribution": round(config.weights.prior * w_norm, 4),
                "weighted_contribution_pct": round(config.weights.prior * w_norm * 100, 2),
            },
        },
        "frequency": {
            "freq_hits_F": score_rec.freq_hits if score_rec else 0,
            "freq_window": score_rec.freq_window if score_rec else 0,
            "window_attempts": window_attempts,
            "hit_attempts": sorted(list(hit_attempts), reverse=True),
        },
        "weightage_section": w_info,
        "appearances": contributing_appearances,
    }


def get_subtopic_why(session: Session, node_id: str, run_id: int | None = None, *,
                     target_attempt_id: str | None = None,
                     taxonomy_version_id: int | None = None,
                     config_hash: str | None = None) -> dict[str, Any]:
    """Explain persisted snapshot contributions, never current corpus fragments."""
    run = session.get(ScoreRun, run_id) if run_id is not None else get_current_score_run(
        session, target_attempt_id, taxonomy_version_id, config_hash)
    if run and (run.status != "ok" or run.shadow or
                run.taxonomy_version_id != taxonomy_version_id or
                (target_attempt_id is not None and run.target_attempt_id != target_attempt_id)):
        raise ValueError("Only successful non-shadow runs matching the target attempt and taxonomy may be explained")
    from caf_l0.hierarchy import ancestor_at, version_nodes
    nodes = {node.id: node for node in version_nodes(session, taxonomy_version_id)}
    node = nodes.get(node_id)
    if node is None or node.level != "subtopic":
        raise ValueError(f"Subtopic node not found in selected taxonomy: {node_id}")
    paper = session.get(Paper, node.paper_id)
    chapter = ancestor_at(node_id, nodes, "chapter")
    topic = ancestor_at(node_id, nodes, "topic")
    identity = {"id": run.id, "version": run.scoring_version,
                "target_attempt_id": run.target_attempt_id, "taxonomy_version_id": run.taxonomy_version_id,
                "computed_at": run.finished_at.isoformat() if run.finished_at else None,
                "corpus_generation": run.corpus_generation, "config_hash": run.config_hash} if run else None
    subtopic = {"id": node.id, "name": node.name, "applicable": True,
               "paper": {"id": paper.id, "code": paper.code, "name": paper.name} if paper else None,
               "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
               "topic": {"id": topic.id, "name": topic.name} if topic else None}
    score = session.get(SubtopicScore, (run.id, node_id)) if run else None
    if score is None:
        return {"node_id": node_id, "explanation_status": "no_score_run" if run is None else "score_unavailable",
                "error": "No successful score snapshot is available for this context.",
                "configuration_source": None, "score_run": identity, "subtopic": subtopic,
                "importance_breakdown": {"importance": None, "known_weighted_subtotal": None,
                    "weights": None, "exam": None, "practice": None, "weightage_prior": None},
                "frequency": None, "weightage_section": None, "appearances": []}
    if not score.evidence or score.evidence.get("semantics_version") != "phase6-v1":
        return get_legacy_subtopic_why(session, node_id, run.id, target_attempt_id=target_attempt_id)
    evidence = score.evidence
    components = evidence["components"]
    def display_component(signal: str, suffix: str) -> dict[str, Any]:
        item = components[signal]
        value = item["normalized"]
        return {"available": item["available"],
                "unavailable_reason": None if item["available"] else (
                    "Reviewed, version-bound official priors are unavailable." if signal == "prior" else
                    "No usable reviewed evidence is available for this component."),
                "weight_prior_W" if signal == "prior" else f"score_{suffix}": item["raw"],
                f"paper_max_{suffix}": item["denominator"], f"normalized_{suffix}_hat": value,
                f"normalized_{suffix}_pct": value * 100 if value is not None else None,
                "weighted_contribution": item["weighted_contribution"],
                "weighted_contribution_pct": item["weighted_contribution"] * 100 if item["available"] else None}
    frequency = evidence["frequency"]
    return {"node_id": node_id, "explanation_status": "available" if score.importance is not None else "partial_evidence",
            "error": None, "configuration_source": "snapshot", "score_run": identity, "subtopic": subtopic,
            "importance_breakdown": {"importance": score.importance,
                "known_weighted_subtotal": evidence["known_weighted_subtotal"],
                "weights": {signal: components[signal]["weight"] for signal in components},
                "formula": "I = wE × E_normalized + wP × P_normalized + wW × W_normalized",
                "exam": display_component("exam", "E"), "practice": display_component("practice", "P"),
                "weightage_prior": display_component("prior", "W")},
            "frequency": {"available": frequency["available"],
                "freq_hits_F": frequency["numerator"] if frequency["available"] else None,
                "freq_window": frequency["denominator"], "window_attempts": frequency["window_attempts"],
                "hit_attempts": frequency["hit_attempts"]},
            "weightage_section": None, "prior_source": evidence["prior_source"],
            "appearances": evidence["contributions"], "coverage_exclusions": evidence["coverage_exclusions"]}
