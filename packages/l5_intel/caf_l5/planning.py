"""Next-week study planning engine with budget allocation and priority scoring."""

import math
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Progress, Settings as AppSettingsModel
from caf_db.models.intel import SubtopicScore
from caf_db.models.ref import Node, Paper, WeightageMember, WeightageSection
from caf_l5.config import load_scoring_config
from caf_l5.service import get_current_score_run, is_subtopic_weak


def generate_study_plan(
    session: Session,
    user_id: int = 1,
    paper_id: str | None = None,
    group_no: int | None = None,
    hours_per_week: float | None = None,
    minutes_per_subtopic: int | None = None,
) -> dict[str, Any]:
    """Generate next-week study plan:
    
    1. budget_items = floor(hours_per_week * 60 / minutes_per_subtopic)
    2. cands = applicable subtopics with status in {not_started, in_progress}
    3. score(s) = I(s) + weak_boost * [weak(s)] + in_progress_boost * [status=in_progress]
    4. sort cands by score desc
    5. pick greedily, skipping s if its chapter already has per_chapter_cap picks, until budget_items
    6. reason(s) = template from facts
    """
    config = load_scoring_config()

    # 1. Resolve budget constraints
    app_settings = session.query(AppSettingsModel).where(AppSettingsModel.user_id == user_id).first()
    if hours_per_week is None:
        hours_per_week = float(app_settings.hours_per_week) if app_settings else 20.0
    if minutes_per_subtopic is None:
        minutes_per_subtopic = int(app_settings.minutes_per_subtopic) if app_settings else 45

    if minutes_per_subtopic <= 0:
        minutes_per_subtopic = 45
    budget_items = math.floor((hours_per_week * 60) / minutes_per_subtopic)

    # 2. Fetch current ScoreRun
    current_run = get_current_score_run(session)
    if not current_run:
        return {
            "budget_items": budget_items,
            "total_allocated": 0,
            "hours_per_week": hours_per_week,
            "minutes_per_subtopic": minutes_per_subtopic,
            "items": [],
        }

    # 3. Fetch nodes, topics, chapters, papers, weightages
    all_nodes = session.query(Node).all()
    nodes_by_id = {n.id: n for n in all_nodes}

    # Weightage section map: chapter_id -> WeightageSection
    wm_rows = (
        session.query(WeightageMember.chapter_id, WeightageSection)
        .join(WeightageSection, WeightageSection.id == WeightageMember.section_id)
        .all()
    )
    ch_to_section = {r[0]: r[1] for r in wm_rows}

    # Query all active subtopic scores under current run
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
            Paper.is_current.is_(True),
        )
    )

    if paper_id:
        # Match either exact ID or paper code
        query = query.where(
            (Paper.id == paper_id) | (Paper.code == paper_id.upper())
        )
    if group_no is not None:
        query = query.where(Paper.group_no == group_no)

    results = query.all()

    candidates = []
    for score, node, paper, prog in results:
        status = prog.status if prog else "not_started"
        if status not in ("not_started", "in_progress"):
            # Skip completed subtopics
            continue

        weak = is_subtopic_weak(
            score.applicable, score.freq_hits, score.freq_window, status, config
        )

        # Priority score
        weak_add = config.plan.weak_boost if weak else 0.0
        in_prog_add = config.plan.in_progress_boost if status == "in_progress" else 0.0
        priority_score = score.importance + weak_add + in_prog_add

        # Resolve chapter & topic
        topic = nodes_by_id.get(node.parent_id) if node.parent_id else None
        chapter = nodes_by_id.get(topic.parent_id) if topic and topic.parent_id else None
        chapter_id = chapter.id if chapter else ""
        chapter_name = chapter.name if chapter else ""
        sec = ch_to_section.get(chapter_id)

        # Factual reason generation
        reason_parts = []
        if score.freq_window > 0 and score.freq_hits > 0:
            reason_parts.append(
                f"Asked in {score.freq_hits} of last {score.freq_window} exams ({score.exam_marks_total} marks)"
            )
        elif status == "in_progress":
            reason_parts.append("Already in progress")
        else:
            reason_parts.append("Core syllabus priority")

        if sec:
            reason_parts.append(
                f"weightage section {sec.name}: {sec.min_pct:.0f}-{sec.max_pct:.0f}%"
            )

        reason = "; ".join(reason_parts)

        candidates.append({
            "node_id": node.id,
            "node_name": node.name,
            "paper_id": paper.id,
            "paper_code": paper.code,
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "status": status,
            "importance": score.importance,
            "priority_score": round(priority_score, 4),
            "weak": weak,
            "freq_hits": score.freq_hits,
            "freq_window": score.freq_window,
            "exam_marks_total": score.exam_marks_total,
            "reason": reason,
        })

    # Sort descending by priority_score, then importance
    candidates.sort(key=lambda c: (c["priority_score"], c["importance"]), reverse=True)

    # Greedy allocation with per_chapter_cap
    per_cap = config.plan.per_chapter_cap
    chapter_counts: dict[str, int] = {}
    allocated: list[dict[str, Any]] = []

    for c in candidates:
        ch_id = c["chapter_id"]
        if chapter_counts.get(ch_id, 0) < per_cap:
            allocated.append(c)
            chapter_counts[ch_id] = chapter_counts.get(ch_id, 0) + 1
            if len(allocated) >= budget_items:
                break

    return {
        "budget_items": budget_items,
        "total_allocated": len(allocated),
        "hours_per_week": hours_per_week,
        "minutes_per_subtopic": minutes_per_subtopic,
        "items": allocated,
    }
