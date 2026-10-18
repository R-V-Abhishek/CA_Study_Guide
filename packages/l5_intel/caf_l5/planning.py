"""Budgeted personal planning with an honest syllabus fallback."""
import math
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session, defer
from caf_db.models.app import Progress, Settings
from caf_db.models.intel import SubtopicScore
from caf_db.models.ref import Paper
from caf_l0.hierarchy import ancestor_at, ancestors
from caf_l5.context import context_nodes, context_leaf_ids, resolve_context
from caf_l5.service import selected_papers, is_subtopic_weak


def generate_study_plan(session: Session, user_id: int, paper_id: str | None = None,
                        group_no: int | None = None, hours_per_week: float | None = None,
                        minutes_per_subtopic: int | None = None) -> dict[str, Any]:
    settings = session.get(Settings, user_id)
    context = resolve_context(session, user_id)
    config = context.config
    if context.run and context.run.config_snapshot:
        from caf_l5.config import ScoringConfig
        config = ScoringConfig.model_validate(context.run.config_snapshot)
    hours = float(hours_per_week if hours_per_week is not None else settings.hours_per_week)
    minutes = int(minutes_per_subtopic if minutes_per_subtopic is not None else settings.minutes_per_subtopic)
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("Study hours must be finite and positive")
    if minutes <= 0:
        raise ValueError("Minutes per subtopic must be positive")
    if group_no not in (None, 1, 2):
        raise ValueError("Group must be 1 or 2")
    budget_minutes = math.floor(hours * 60)
    budget_items = budget_minutes // minutes
    nodes = context_nodes(session, context)
    node_map = {node.id: node for node in nodes}
    terminal_ids = context_leaf_ids(session, context)
    papers = {paper.id: paper for paper in session.scalars(sa.select(Paper))}
    allowed = set(selected_papers(session, user_id))
    progress = {row.node_id: row.status for row in session.scalars(
        sa.select(Progress).where(Progress.user_id == user_id))}
    scores = {row.node_id: row for row in session.scalars(sa.select(SubtopicScore).options(
        defer(SubtopicScore.evidence)).where(
        SubtopicScore.score_run_id == context.run.id))} if context.run else {}
    selected_nodes = [node for node in nodes if node.id in terminal_ids
                      and node.paper_id in allowed
                      and (paper_id is None or node.paper_id == paper_id or
                           papers[node.paper_id].code == paper_id.upper())
                      and (group_no is None or papers[node.paper_id].group_no == group_no)]
    selected_nodes.sort(key=lambda node: (papers[node.paper_id].code,
        tuple(ancestor.seq for ancestor in ancestors(node.id, node_map)), node.id))
    # A partially ranked paper cannot produce a scored plan. Select the syllabus
    # basis for all selected papers together so comparisons have one meaning.
    scored = bool(selected_nodes) and all(node.id in scores and
                scores[node.id].importance is not None for node in selected_nodes)
    basis = "scored" if scored else ("syllabus" if context.readiness == "ready" and selected_nodes else "unavailable")
    candidates = []
    for order, node in enumerate(selected_nodes):
        status = progress.get(node.id, "not_started")
        if status not in {"in_progress", "not_started"}:
            continue
        score = scores.get(node.id)
        importance = score.importance if scored else None
        weak = bool(scored and is_subtopic_weak(score.applicable, score.freq_hits,
                    score.freq_window, status, config))
        priority = importance + (config.plan.weak_boost if weak else 0) + (
            config.plan.in_progress_boost if status == "in_progress" else 0) if scored else None
        chapter = ancestor_at(node.id, node_map, "chapter")
        reason = "Already in progress" if status == "in_progress" else "Next in reviewed syllabus order"
        if scored and score.freq_window:
            reason = f"Appeared in {score.freq_hits} of {score.freq_window} usable reviewed attempts"
            if status == "in_progress":
                reason += "; already in progress"
        candidates.append({"node_id": node.id, "node_name": node.name,
            "paper_id": node.paper_id, "paper_code": papers[node.paper_id].code,
            "chapter_id": chapter.id if chapter else node.id,
            "chapter_name": chapter.name if chapter else "", "status": status,
            "importance": importance, "priority_score": round(priority, 4) if priority is not None else None,
            "weak": weak, "freq_hits": score.freq_hits if scored else 0,
            "freq_window": score.freq_window if scored else 0,
            "exam_marks_total": score.exam_marks_total if scored else 0,
            "reason": reason, "_order": order})
    if scored:
        candidates.sort(key=lambda item: (-item["priority_score"], -item["importance"], item["_order"]))
    else:
        candidates.sort(key=lambda item: (item["status"] != "in_progress", item["_order"]))
    allocated = []
    chapters: dict[str, int] = {}
    for item in candidates:
        if len(allocated) >= budget_items:
            break
        chapter = item["chapter_id"]
        if chapters.get(chapter, 0) >= config.plan.per_chapter_cap:
            continue
        chapters[chapter] = chapters.get(chapter, 0) + 1
        item.pop("_order")
        allocated.append(item)
    return {"basis": basis, "budget_items": budget_items, "total_allocated": len(allocated),
            "allocated_minutes": len(allocated) * minutes,
            "unused_minutes": budget_minutes - len(allocated) * minutes,
            "hours_per_week": hours, "minutes_per_subtopic": minutes, "items": allocated,
            "score_run_id": context.run.id if context.run else None, "context": context.identity,
            "freshness": context.freshness,
            "score_unavailable_reason": None if scored else (
                "Historical ranking is unavailable; this plan uses personal progress and reviewed syllabus order."
                if basis == "syllabus" else ("No applicable terminal subtopics are available in the selected papers."
                if context.readiness == "ready" else "An approved target-attempt taxonomy binding is unavailable."))}
