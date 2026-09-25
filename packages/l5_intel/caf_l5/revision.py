"""Revision queue and spaced-repetition engine."""

from datetime import date, datetime, timedelta, timezone
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_db.models.app import Progress, RevisionEvent, Settings as AppSettingsModel
from caf_db.models.intel import SubtopicScore
from caf_db.models.ref import Node, Paper
from caf_l5.service import get_current_score_run


def get_revision_due_list(
    session: Session,
    user_id: int = 1,
    as_of_date: date | None = None,
    paper_id: str | None = None,
) -> list[dict[str, Any]]:
    """Generate spaced-repetition revision due list:
    
    for s with status=done:
       k   = number of revision_events for s since first_done_at
       due = (last_revised_at or first_done_at) + intervals[min(k, len-1)] days
       'shaky' outcome resets k to 0 for that subtopic
    due_list = s with due <= today, ordered by I(s) desc, then overdue days desc
    """
    today = as_of_date or datetime.now(timezone.utc).date()

    # 1. Fetch user revision intervals
    app_settings = session.query(AppSettingsModel).where(AppSettingsModel.user_id == user_id).first()
    intervals = app_settings.revision_intervals if app_settings and app_settings.revision_intervals else [3, 7, 21, 60]

    # 2. Fetch current ScoreRun for importance scores
    current_run = get_current_score_run(session)
    scores_map: dict[str, SubtopicScore] = {}
    if current_run:
        scores = session.query(SubtopicScore).where(SubtopicScore.score_run_id == current_run.id).all()
        scores_map = {s.node_id: s for s in scores}

    # 3. Query completed subtopics for this user
    query = (
        session.query(Progress, Node, Paper)
        .join(Node, Node.id == Progress.node_id)
        .join(Paper, Paper.id == Node.paper_id)
        .where(
            Progress.user_id == user_id,
            Progress.status == "done",
            Progress.first_done_at.is_not(None),
        )
    )

    if paper_id:
        query = query.where((Paper.id == paper_id) | (Paper.code == paper_id.upper()))

    completed_rows = query.all()
    if not completed_rows:
        return []

    # 4. Fetch all revision events for this user
    all_events = (
        session.query(RevisionEvent)
        .where(RevisionEvent.user_id == user_id)
        .order_by(RevisionEvent.at.asc())
        .all()
    )
    events_by_node: dict[str, list[RevisionEvent]] = {}
    for ev in all_events:
        events_by_node.setdefault(ev.node_id, []).append(ev)

    due_list = []
    for prog, node, paper in completed_rows:
        first_done = prog.first_done_at
        last_revised = prog.last_revised_at or first_done

        # Compute k with 'shaky' resets
        k = 0
        node_events = events_by_node.get(node.id, [])
        for ev in node_events:
            if ev.at >= first_done:
                if ev.outcome == "shaky":
                    k = 0
                elif ev.outcome == "ok":
                    k += 1

        interval_days = intervals[min(k, len(intervals) - 1)]
        base_date = last_revised.date() if isinstance(last_revised, datetime) else last_revised
        due_date = base_date + timedelta(days=interval_days)

        if due_date <= today:
            overdue_days = (today - due_date).days
            sc = scores_map.get(node.id)
            importance = sc.importance if sc else 0.0

            due_list.append({
                "node_id": node.id,
                "node_name": node.name,
                "paper_id": paper.id,
                "paper_code": paper.code,
                "importance": importance,
                "due_date": due_date.isoformat(),
                "overdue_days": overdue_days,
                "revision_count_k": k,
                "interval_days": interval_days,
                "first_done_at": first_done.isoformat() if first_done else None,
                "last_revised_at": last_revised.isoformat() if last_revised else None,
            })

    # Order by I(s) desc, then overdue days desc
    due_list.sort(key=lambda item: (item["importance"], item["overdue_days"]), reverse=True)
    return due_list


def record_revision_outcome(
    session: Session,
    node_id: str,
    outcome: str,
    user_id: int = 1,
) -> dict[str, Any]:
    """Record revision outcome ('ok' or 'shaky') and update last_revised_at."""
    if outcome not in ("ok", "shaky"):
        raise ValueError(f"Invalid revision outcome '{outcome}'. Must be 'ok' or 'shaky'.")

    node = session.get(Node, node_id)
    if not node:
        raise ValueError(f"Node '{node_id}' not found.")

    progress = session.get(Progress, (user_id, node_id))
    now = datetime.now(timezone.utc)

    if not progress:
        progress = Progress(
            user_id=user_id,
            node_id=node_id,
            status="done",
            first_done_at=now,
            last_revised_at=now,
            status_changed_at=now,
        )
        session.add(progress)
    else:
        progress.last_revised_at = now
        if progress.status != "done":
            progress.status = "done"
            if not progress.first_done_at:
                progress.first_done_at = now

    event = RevisionEvent(
        user_id=user_id,
        node_id=node_id,
        outcome=outcome,
        at=now,
    )
    session.add(event)
    session.commit()

    return {
        "event_id": event.id,
        "node_id": node_id,
        "outcome": outcome,
        "at": now.isoformat(),
        "last_revised_at": progress.last_revised_at.isoformat(),
    }
