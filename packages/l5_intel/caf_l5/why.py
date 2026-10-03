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


def get_subtopic_why(
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
            raise ValueError("Score context does not match target attempt and taxonomy version")
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

    target_att = session.get(Attempt, score_run.target_attempt_id)
    t_year = target_att.exam_year if target_att else 2026
    t_month = target_att.exam_month if target_att else 5

    # 4. Fetch all attempts for lookup
    all_attempts = {att.id: att for att in session.query(Attempt).all()}

    # 5. Fetch frequency window for paper
    # Attempts in window for this paper
    paper_cov = (
        session.query(IngestionCoverage)
        .where(
            IngestionCoverage.score_run_id == score_run.id,
            IngestionCoverage.paper_id == subtopic.paper_id,
            IngestionCoverage.exam_published.is_(True),
        )
        .all()
    )
    published_exam_attempts = []
    for c in paper_cov:
        att = all_attempts.get(c.attempt_id)
        if att:
            age = compute_age_months(att.exam_year, att.exam_month, t_year, t_month)
            if age >= 0:
                published_exam_attempts.append(att)
    published_exam_attempts.sort(key=lambda a: (a.exam_year, a.exam_month), reverse=True)
    window_attempts = [a.id for a in published_exam_attempts[: config.freq_window_attempts]]
    window_set = set(window_attempts)

    # 6. Fetch appearances tagged to this node or its parent topic / chapter
    relevant_node_ids = [node_id]
    if topic:
        relevant_node_ids.append(topic.id)
    if chapter:
        relevant_node_ids.append(chapter.id)

    app_tags = (
        session.query(Appearance, AppearanceTag)
        .join(AppearanceTag, AppearanceTag.appearance_id == Appearance.id)
        .where(
            AppearanceTag.node_id.in_(relevant_node_ids),
            Appearance.status == "published",
        )
        .all()
    )

    # Compute subtopic counts under topic and chapter to scale share if tagged at higher level
    topic_sub_count = (len(descendant_leaves(topic.id, nodes)) or 1) if topic else 1
    chapter_sub_count = (len(descendant_leaves(chapter.id, nodes)) or 1) if chapter else 1

    contributing_appearances = []
    exam_total_contrib = 0.0
    practice_total_contrib = 0.0
    hit_attempts = set()

    for app, tag in app_tags:
        att = all_attempts.get(app.attempt_id)
        att_year = att.exam_year if att else 2024
        att_month = att.exam_month if att else 5
        age = compute_age_months(att_year, att_month, t_year, t_month)

        # Scale share if tag was at topic or chapter level
        s_share = tag.share
        if tag.node_id == (topic.id if topic else None):
            s_share = tag.share / max(topic_sub_count, 1)
        elif tag.node_id == (chapter.id if chapter else None):
            s_share = tag.share / max(chapter_sub_count, 1)

        m, kappa, lambda_val = calculate_attributed_marks(
            marks=app.marks,
            share=s_share,
            source_paper_id=app.source_paper_id,
            target_node_paper_id=subtopic.paper_id,
            law_stale=app.law_stale,
            config=config,
        )

        half_life = config.half_life_exam_months if app.signal_class == "exam" else config.half_life_practice_months
        decay_factor = compute_decay(age, half_life) if age >= 0 else 0.0
        contribution = m * decay_factor if age >= 0 else 0.0

        in_window = app.attempt_id in window_set and app.signal_class == "exam"
        if in_window:
            hit_attempts.add(app.attempt_id)

        if age >= 0:
            if app.signal_class == "exam":
                exam_total_contrib += contribution
            elif app.signal_class == "practice":
                practice_total_contrib += contribution

        contributing_appearances.append({
            "appearance_id": app.id,
            "attempt_id": app.attempt_id,
            "signal_class": app.signal_class,
            "display_label": app.display_label,
            "gist": app.gist,
            "marks": app.marks,
            "tag_role": tag.role,
            "tag_level": "subtopic" if tag.node_id == node_id else ("topic" if topic and tag.node_id == topic.id else "chapter"),
            "share": round(s_share, 4),
            "kappa": kappa,
            "lambda_val": lambda_val,
            "attributed_marks_m": round(m, 4),
            "age_months": age,
            "half_life_months": half_life,
            "decay": round(decay_factor, 6),
            "contribution": round(contribution, 4),
            "in_freq_window": in_window,
            "ignored_post_target": age < 0,
            "law_stale": app.law_stale,
        })

    # Sort appearances by attempt date descending
    contributing_appearances.sort(key=lambda a: a["attempt_id"], reverse=True)

    # 7. Weightage section details
    w_info = None
    if chapter:
        w_member = session.query(WeightageMember).where(
            WeightageMember.chapter_id == chapter.id
        ).first()
        if w_member:
            sec = session.get(WeightageSection, w_member.section_id)
            if sec:
                p_max = paper.max_marks if paper else 100
                sec_mid = (float(sec.min_pct) + float(sec.max_pct)) / 2.0
                sec_marks = (sec_mid / 100.0) * p_max

                # Count applicable subtopics under all chapters in this section
                all_ch_ids = [
                    m.chapter_id for m in session.query(WeightageMember).where(
                        WeightageMember.section_id == sec.id
                    ).all()
                ]
                # Find all subtopics under these chapters
                subtopic_count = len({leaf for chapter_id in all_ch_ids
                                     for leaf in descendant_leaves(chapter_id, nodes)})

                w_info = {
                    "section_id": sec.id,
                    "section_name": sec.name,
                    "min_pct": float(sec.min_pct),
                    "max_pct": float(sec.max_pct),
                    "midpoint_pct": sec_mid,
                    "section_marks": round(sec_marks, 2),
                    "applicable_subtopics_in_section": subtopic_count,
                    "subtopic_weight_prior_W": round(score_rec.weight_prior if score_rec else 0.0, 4),
                }

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
        "score_run": {
            "id": score_run.id,
            "version": score_run.scoring_version,
            "target_attempt_id": score_run.target_attempt_id,
            "computed_at": score_run.finished_at.isoformat() if score_run.finished_at else None,
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
