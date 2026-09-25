from datetime import date, datetime, timezone
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.app import (
    MockTest,
    Note,
    Progress,
    ProgressEvent,
    RevisionEvent,
    Settings,
    UserAccount,
)
from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.intel import SubtopicScore
from caf_db.models.ref import Node, Paper, WeightageMember, WeightageSection
from caf_l5 import (
    compute_weighted_coverage,
    generate_study_plan,
    get_current_score_run,
    get_ingestion_coverage_matrix,
    get_revision_due_list,
    get_subtopic_scores_for_paper,
    get_subtopic_why,
    get_weak_subtopics,
    is_subtopic_weak,
    record_revision_outcome,
)

router = APIRouter(prefix="/api/v1")


def get_db():
    factory = get_session_factory()
    with factory() as session:
        yield session


def ensure_default_user(session: Session) -> UserAccount:
    settings = get_settings()
    user_id = settings.app.user_id
    user = session.get(UserAccount, user_id)
    if not user:
        user = UserAccount(id=user_id, name="Primary Aspirant")
        session.add(user)
        session.flush()

        app_settings = Settings(
            user_id=user_id,
            target_attempt_id=settings.app.target_attempt_id,
            hours_per_week=20.0,
            minutes_per_subtopic=45,
            revision_intervals=[3, 7, 21, 60],
        )
        session.add(app_settings)
        session.commit()
    return user


# ==============================================================================
# Schemas
# ==============================================================================

class ProgressUpdateRequest(BaseModel):
    status: Literal["not_started", "in_progress", "done"]


class NoteUpdateRequest(BaseModel):
    notes: str


class RevisionLogRequest(BaseModel):
    outcome: Literal["ok", "shaky"]


class MockTestCreateRequest(BaseModel):
    paper_id: str
    attempt_id: str | None = None
    label: str | None = None
    score: float
    max_score: float = 100.0
    taken_on: date
    notes: str | None = None


class SubtopicItem(BaseModel):
    id: str
    name: str
    seq: int
    status: str
    notes: str | None = None
    first_done_at: datetime | None = None
    last_revised_at: datetime | None = None
    importance: float = 0.0
    freq_hits: int = 0
    freq_window: int = 0
    weak: bool = False
    applicable: bool = True


class TopicItem(BaseModel):
    id: str
    name: str
    seq: int
    subtopics: list[SubtopicItem]


class ChapterItem(BaseModel):
    id: str
    name: str
    seq: int
    weightage_min_pct: float | None = None
    weightage_max_pct: float | None = None
    weightage_section_name: str | None = None
    total_subtopics: int = 0
    completed_subtopics: int = 0
    progress_pct: float = 0.0
    topics: list[TopicItem]


class PaperSummary(BaseModel):
    id: str
    code: str
    name: str
    group_no: int | None
    total_subtopics: int
    completed_subtopics: int
    raw_progress_pct: float
    weighted_coverage_pct: float


# ==============================================================================
# Endpoints
# ==============================================================================

@router.get("/papers", response_model=list[PaperSummary])
def list_papers(session: Session = Depends(get_db)):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    papers = session.execute(
        sa.select(Paper).where(Paper.is_current.is_(True)).order_by(Paper.code)
    ).scalars().all()

    summaries = []
    for p in papers:
        # Get all subtopics for this paper
        subtopics = session.execute(
            sa.select(Node.id, Node.parent_id).where(
                Node.paper_id == p.id, Node.level == "subtopic", Node.status == "active"
            )
        ).all()
        total_sub = len(subtopics)

        sub_ids = [s.id for s in subtopics]
        completed_count = 0
        if sub_ids:
            completed_count = session.execute(
                sa.select(sa.func.count(Progress.node_id)).where(
                    Progress.user_id == user_id,
                    Progress.node_id.in_(sub_ids),
                    Progress.status == "done",
                )
            ).scalar() or 0

        raw_pct = (completed_count / total_sub * 100.0) if total_sub > 0 else 0.0

        # Compute weighted coverage using chapter weightage midpoints
        # 1. Fetch chapters and their weightage sections
        ch_rows = session.execute(
            sa.select(
                Node.id,
                WeightageSection.min_pct,
                WeightageSection.max_pct,
            )
            .join(WeightageMember, WeightageMember.chapter_id == Node.id, isouter=True)
            .join(WeightageSection, WeightageSection.id == WeightageMember.section_id, isouter=True)
            .where(Node.paper_id == p.id, Node.level == "chapter")
        ).all()

        total_weight = 0.0
        earned_weight = 0.0

        for ch_id, min_pct, max_pct in ch_rows:
            # Chapter midpoint weight
            ch_mid = ((float(min_pct) + float(max_pct)) / 2.0) if min_pct and max_pct else 10.0
            total_weight += ch_mid

            # Subtopics in this chapter
            topic_ids = sa.select(Node.id).where(Node.parent_id == ch_id, Node.level == "topic")
            ch_subs = session.execute(
                sa.select(Node.id).where(Node.parent_id.in_(topic_ids), Node.level == "subtopic")
            ).scalars().all()

            if ch_subs:
                done_in_ch = session.execute(
                    sa.select(sa.func.count(Progress.node_id)).where(
                        Progress.user_id == user_id,
                        Progress.node_id.in_(ch_subs),
                        Progress.status == "done",
                    )
                ).scalar() or 0
                ch_ratio = done_in_ch / len(ch_subs)
                earned_weight += ch_mid * ch_ratio

        weighted_pct = (earned_weight / total_weight * 100.0) if total_weight > 0 else raw_pct

        summaries.append(
            PaperSummary(
                id=p.id,
                code=p.code,
                name=p.name,
                group_no=p.group_no,
                total_subtopics=total_sub,
                completed_subtopics=completed_count,
                raw_progress_pct=round(raw_pct, 1),
                weighted_coverage_pct=round(weighted_pct, 1),
            )
        )

    return summaries


@router.get("/papers/{paper_id}/tree")
def get_paper_tree(paper_id: str, session: Session = Depends(get_db)):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    # Fetch all nodes for this paper
    nodes = session.execute(
        sa.select(Node).where(Node.paper_id == paper_id, Node.status == "active").order_by(Node.seq)
    ).scalars().all()

    # User progress & notes map
    progress_rows = session.execute(
        sa.select(Progress).where(Progress.user_id == user_id)
    ).scalars().all()
    progress_map = {p.node_id: p for p in progress_rows}

    note_rows = session.execute(
        sa.select(Note).where(Note.user_id == user_id)
    ).scalars().all()
    note_map = {n.node_id: n.body for n in note_rows}

    # Weightages map by chapter
    weightage_rows = session.execute(
        sa.select(
            WeightageMember.chapter_id,
            WeightageSection.name,
            WeightageSection.min_pct,
            WeightageSection.max_pct,
        )
        .join(WeightageSection, WeightageSection.id == WeightageMember.section_id)
        .where(WeightageSection.paper_id == paper_id)
    ).all()
    w_map = {r.chapter_id: r for r in weightage_rows}

    # Organize into tree
    chapters_by_id = {}
    topics_by_parent = {}
    subtopics_by_parent = {}

    for n in nodes:
        if n.level == "chapter":
            chapters_by_id[n.id] = n
        elif n.level == "topic":
            topics_by_parent.setdefault(n.parent_id, []).append(n)
        elif n.level == "subtopic":
            subtopics_by_parent.setdefault(n.parent_id, []).append(n)

    # Load intelligence scores for this paper
    scores_map = get_subtopic_scores_for_paper(session, paper_id)

    result_chapters = []
    for ch_id, ch in sorted(chapters_by_id.items(), key=lambda x: x[1].seq):
        topics_out = []
        ch_sub_count = 0
        ch_sub_done = 0

        for t in sorted(topics_by_parent.get(ch_id, []), key=lambda x: x.seq):
            subs_out = []
            for s in sorted(subtopics_by_parent.get(t.id, []), key=lambda x: x.seq):
                ch_sub_count += 1
                pr = progress_map.get(s.id)
                status = pr.status if pr else "not_started"
                if status == "done":
                    ch_sub_done += 1

                sc = scores_map.get(s.id)
                importance = sc.importance if sc else 0.0
                freq_hits = sc.freq_hits if sc else 0
                freq_window = sc.freq_window if sc else 0
                applicable = sc.applicable if sc else True
                weak = is_subtopic_weak(applicable, freq_hits, freq_window, status)

                subs_out.append(
                    SubtopicItem(
                        id=s.id,
                        name=s.name,
                        seq=s.seq,
                        status=status,
                        notes=note_map.get(s.id),
                        first_done_at=pr.first_done_at if pr else None,
                        last_revised_at=pr.last_revised_at if pr else None,
                        importance=importance,
                        freq_hits=freq_hits,
                        freq_window=freq_window,
                        weak=weak,
                        applicable=applicable,
                    )
                )
            topics_out.append(TopicItem(id=t.id, name=t.name, seq=t.seq, subtopics=subs_out))

        w_info = w_map.get(ch_id)
        progress_pct = (ch_sub_done / ch_sub_count * 100.0) if ch_sub_count > 0 else 0.0

        result_chapters.append(
            ChapterItem(
                id=ch.id,
                name=ch.name,
                seq=ch.seq,
                weightage_min_pct=float(w_info.min_pct) if w_info else None,
                weightage_max_pct=float(w_info.max_pct) if w_info else None,
                weightage_section_name=w_info.name if w_info else None,
                total_subtopics=ch_sub_count,
                completed_subtopics=ch_sub_done,
                progress_pct=round(progress_pct, 1),
                topics=topics_out,
            )
        )

    return {
        "paper_id": paper.id,
        "code": paper.code,
        "name": paper.name,
        "chapters": result_chapters,
    }


@router.get("/tree")
def get_tree_by_query(
    paper: str,
    session: Session = Depends(get_db),
):
    """Retrieve paper taxonomy tree by code (e.g. P1) or ID (s2023.P1)."""
    paper_row = session.execute(
        sa.select(Paper).where((Paper.code == paper.upper()) | (Paper.id == paper))
    ).scalar_one_or_none()
    if not paper_row:
        raise HTTPException(status_code=404, detail=f"Paper '{paper}' not found")
    return get_paper_tree(paper_row.id, session)


@router.get("/subtopics/{node_id}")
def get_subtopic_detail(node_id: str, session: Session = Depends(get_db)):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    subtopic = session.get(Node, node_id)
    if not subtopic or subtopic.level != "subtopic":
        raise HTTPException(status_code=404, detail="Subtopic not found")

    topic = session.get(Node, subtopic.parent_id) if subtopic.parent_id else None
    chapter = session.get(Node, topic.parent_id) if topic and topic.parent_id else None
    paper = session.get(Paper, subtopic.paper_id) if subtopic.paper_id else None

    progress = session.get(Progress, (user_id, node_id))
    note = session.get(Note, (user_id, node_id))

    # Weightage for this chapter
    w_info = None
    if chapter:
        w_row = session.execute(
            sa.select(WeightageSection)
            .join(WeightageMember, WeightageMember.section_id == WeightageSection.id)
            .where(WeightageMember.chapter_id == chapter.id)
        ).scalar_one_or_none()
        if w_row:
            w_info = {
                "section_name": w_row.name,
                "min_pct": float(w_row.min_pct),
                "max_pct": float(w_row.max_pct),
            }

    # Published exam appearances (C4 inline history)
    relevant_node_ids = [node_id]
    if topic:
        relevant_node_ids.append(topic.id)
    if chapter:
        relevant_node_ids.append(chapter.id)

    appearances = session.execute(
        sa.select(Appearance)
        .join(AppearanceTag, AppearanceTag.appearance_id == Appearance.id)
        .where(AppearanceTag.node_id.in_(relevant_node_ids), Appearance.status == "published")
        .order_by(Appearance.attempt_id.desc())
    ).scalars().all()

    appearances_out = [
        {
            "id": a.id,
            "attempt_id": a.attempt_id,
            "signal_class": a.signal_class,
            "display_label": a.display_label,
            "marks": a.marks,
            "gist": a.gist,
            "official_url": a.official_url,
            "page_start": a.page_start,
            "page_end": a.page_end,
            "law_stale": a.law_stale,
        }
        for a in appearances
    ]

    # Intelligence scores for this subtopic
    current_run = get_current_score_run(session)
    score_rec = None
    if current_run:
        score_rec = session.query(SubtopicScore).where(
            SubtopicScore.score_run_id == current_run.id,
            SubtopicScore.node_id == node_id,
        ).first()

    status_str = progress.status if progress else "not_started"
    score_out = {
        "importance": score_rec.importance if score_rec else 0.0,
        "exam_score": score_rec.exam_score if score_rec else 0.0,
        "practice_score": score_rec.practice_score if score_rec else 0.0,
        "weight_prior": score_rec.weight_prior if score_rec else 0.0,
        "freq_hits": score_rec.freq_hits if score_rec else 0,
        "freq_window": score_rec.freq_window if score_rec else 0,
        "exam_marks_total": score_rec.exam_marks_total if score_rec else 0,
        "exam_count": score_rec.exam_count if score_rec else 0,
        "practice_count": score_rec.practice_count if score_rec else 0,
        "first_exam_attempt": score_rec.first_exam_attempt if score_rec else None,
        "last_exam_attempt": score_rec.last_exam_attempt if score_rec else None,
        "weak": is_subtopic_weak(
            score_rec.applicable if score_rec else True,
            score_rec.freq_hits if score_rec else 0,
            score_rec.freq_window if score_rec else 0,
            status_str,
        ),
        "applicable": score_rec.applicable if score_rec else True,
    }

    return {
        "id": subtopic.id,
        "name": subtopic.name,
        "paper": {"id": paper.id, "code": paper.code, "name": paper.name} if paper else None,
        "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
        "topic": {"id": topic.id, "name": topic.name} if topic else None,
        "status": status_str,
        "notes": note.body if note else None,
        "status_changed_at": progress.status_changed_at if progress else None,
        "first_done_at": progress.first_done_at if progress else None,
        "last_revised_at": progress.last_revised_at if progress else None,
        "weightage": w_info,
        "score": score_out,
        "appearances": appearances_out,
    }


@router.put("/subtopics/{node_id}/progress")
def update_subtopic_progress(
    node_id: str,
    req: ProgressUpdateRequest,
    session: Session = Depends(get_db),
):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    subtopic = session.get(Node, node_id)
    if not subtopic or subtopic.level != "subtopic":
        raise HTTPException(status_code=404, detail="Subtopic not found")

    progress = session.get(Progress, (user_id, node_id))
    old_status = progress.status if progress else "not_started"
    now = datetime.now(timezone.utc)

    if not progress:
        progress = Progress(
            user_id=user_id,
            node_id=node_id,
            status=req.status,
            status_changed_at=now,
            first_done_at=now if req.status == "done" else None,
        )
        session.add(progress)
    else:
        progress.status = req.status
        progress.status_changed_at = now
        if req.status == "done" and not progress.first_done_at:
            progress.first_done_at = now
        elif req.status == "done":
            progress.last_revised_at = now

    # Log event
    event = ProgressEvent(
        user_id=user_id,
        node_id=node_id,
        from_status=old_status,
        to_status=req.status,
        at=now,
    )
    session.add(event)
    session.commit()

    return {"status": progress.status, "node_id": node_id, "updated_at": now.isoformat()}


@router.put("/subtopics/{node_id}/notes")
def update_subtopic_notes(
    node_id: str,
    req: NoteUpdateRequest,
    session: Session = Depends(get_db),
):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    subtopic = session.get(Node, node_id)
    if not subtopic or subtopic.level != "subtopic":
        raise HTTPException(status_code=404, detail="Subtopic not found")

    note = session.get(Note, (user_id, node_id))
    now = datetime.now(timezone.utc)
    if not note:
        note = Note(user_id=user_id, node_id=node_id, body=req.notes, updated_at=now)
        session.add(note)
    else:
        note.body = req.notes
        note.updated_at = now

    session.commit()
    return {"node_id": node_id, "notes": note.body, "updated_at": now.isoformat()}


@router.get("/dashboard")
def get_dashboard(session: Session = Depends(get_db)):
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    # Overall subtopic counts
    all_subtopics = session.execute(
        sa.select(Node.id).where(Node.level == "subtopic", Node.status == "active")
    ).scalars().all()
    total_subtopics = len(all_subtopics)

    done_subtopics = session.execute(
        sa.select(sa.func.count(Progress.node_id)).where(
            Progress.user_id == user_id,
            Progress.status == "done",
            Progress.node_id.in_(all_subtopics),
        )
    ).scalar() or 0

    in_progress_subtopics = session.execute(
        sa.select(sa.func.count(Progress.node_id)).where(
            Progress.user_id == user_id,
            Progress.status == "in_progress",
            Progress.node_id.in_(all_subtopics),
        )
    ).scalar() or 0

    overall_pct = (done_subtopics / total_subtopics * 100.0) if total_subtopics > 0 else 0.0

    # Group 1 and Group 2 Breakdown
    group_stats = {1: {"total": 0, "done": 0}, 2: {"total": 0, "done": 0}}
    papers = session.execute(sa.select(Paper).where(Paper.is_current.is_(True))).scalars().all()

    for p in papers:
        g = p.group_no or 1
        p_subs = session.execute(
            sa.select(Node.id).where(Node.paper_id == p.id, Node.level == "subtopic")
        ).scalars().all()
        p_done = session.execute(
            sa.select(sa.func.count(Progress.node_id)).where(
                Progress.user_id == user_id,
                Progress.status == "done",
                Progress.node_id.in_(p_subs),
            )
        ).scalar() or 0
        group_stats[g]["total"] += len(p_subs)
        group_stats[g]["done"] += p_done

    g1_pct = (group_stats[1]["done"] / group_stats[1]["total"] * 100.0) if group_stats[1]["total"] else 0.0
    g2_pct = (group_stats[2]["done"] / group_stats[2]["total"] * 100.0) if group_stats[2]["total"] else 0.0

    # Recent activity
    recent_events = session.execute(
        sa.select(ProgressEvent, Node.name, Paper.code)
        .join(Node, Node.id == ProgressEvent.node_id)
        .join(Paper, Paper.id == Node.paper_id)
        .where(ProgressEvent.user_id == user_id)
        .order_by(ProgressEvent.at.desc())
        .limit(10)
    ).all()

    activity = [
        {
            "node_id": ev.node_id,
            "node_name": node_name,
            "paper_code": paper_code,
            "from_status": ev.from_status,
            "to_status": ev.to_status,
            "at": ev.at.isoformat(),
        }
        for ev, node_name, paper_code in recent_events
    ]

    # L5 Intelligence integrations
    current_run = get_current_score_run(session)
    weighted_cov = compute_weighted_coverage(session, user_id=user_id)
    weak_items = get_weak_subtopics(session, user_id=user_id, limit=10)
    coverage_matrix = get_ingestion_coverage_matrix(
        session, current_run.id if current_run else None
    )

    # M6 Planning and revision previews
    plan_data = generate_study_plan(session, user_id=user_id)
    plan_preview = plan_data.get("items", [])[:5]
    revision_due = get_revision_due_list(session, user_id=user_id)

    return {
        "target_attempt": settings.app.target_attempt_id,
        "score_run_id": current_run.id if current_run else None,
        "total_subtopics": total_subtopics,
        "done_subtopics": done_subtopics,
        "in_progress_subtopics": in_progress_subtopics,
        "overall_progress_pct": round(overall_pct, 1),
        "group1_progress_pct": round(g1_pct, 1),
        "group2_progress_pct": round(g2_pct, 1),
        "weighted_coverage": weighted_cov,
        "weak_subtopics": weak_items,
        "ingestion_coverage": coverage_matrix.get("coverage", []),
        "plan_preview": plan_preview,
        "revision_due_count": len(revision_due),
        "recent_activity": activity,
    }


@router.get("/meta")
def get_meta(session: Session = Depends(get_db)):
    """System metadata and ingestion coverage indicator."""
    settings = get_settings()
    current_run = get_current_score_run(session)
    coverage_matrix = get_ingestion_coverage_matrix(
        session, current_run.id if current_run else None
    )
    return {
        "taxonomy_version": "v1",
        "scoring_version": current_run.scoring_version if current_run else "v1",
        "api_version": "v1",
        "target_attempt": settings.app.target_attempt_id,
        "score_run_id": current_run.id if current_run else None,
        "score_run_computed_at": current_run.finished_at.isoformat() if current_run and current_run.finished_at else None,
        "ingestion_coverage": coverage_matrix.get("coverage", []),
    }


@router.get("/why/subtopic/{node_id}")
def api_get_subtopic_why(node_id: str, session: Session = Depends(get_db)):
    """Explainability payload for a subtopic score."""
    try:
        return get_subtopic_why(session, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ==============================================================================
# M6: Planning, Revision Queue & Mock Tests Endpoints
# ==============================================================================

@router.get("/plan")
def api_get_study_plan(
    paper: str | None = Query(None, description="Optional paper code/ID filter, e.g. P1"),
    group: int | None = Query(None, description="Optional group filter, e.g. 1 or 2"),
    hours: float | None = Query(None, description="Optional override for study hours per week"),
    session: Session = Depends(get_db),
):
    """Retrieve next-week study plan with allocated subtopics and factual reasons."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    plan = generate_study_plan(
        session=session,
        user_id=user_id,
        paper_id=paper,
        group_no=group,
        hours_per_week=hours,
    )
    return plan


@router.get("/revision/due")
def api_get_revision_due(
    paper: str | None = Query(None, description="Optional paper code/ID filter"),
    session: Session = Depends(get_db),
):
    """Retrieve spaced-repetition revision queue due items."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    due_items = get_revision_due_list(session=session, user_id=user_id, paper_id=paper)
    return {
        "total_due": len(due_items),
        "items": due_items,
    }


@router.post("/subtopics/{node_id}/revisions")
def api_record_subtopic_revision(
    node_id: str,
    req: RevisionLogRequest,
    session: Session = Depends(get_db),
):
    """Record revision outcome ('ok' or 'shaky') and update last_revised_at."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    try:
        res = record_revision_outcome(
            session=session,
            node_id=node_id,
            outcome=req.outcome,
            user_id=user_id,
        )
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/mock-tests")
def api_list_mock_tests(
    paper: str | None = Query(None, description="Optional paper filter"),
    session: Session = Depends(get_db),
):
    """List mock test records for the student."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    query = sa.select(MockTest, Paper.code).join(Paper, Paper.id == MockTest.paper_id).where(MockTest.user_id == user_id)
    if paper:
        query = query.where((Paper.code == paper.upper()) | (Paper.id == paper))
    query = query.order_by(MockTest.taken_on.desc())

    rows = session.execute(query).all()
    tests = []
    for mt, p_code in rows:
        pct = (float(mt.score) / float(mt.max_score) * 100.0) if float(mt.max_score) > 0 else 0.0
        tests.append({
            "id": mt.id,
            "paper_id": mt.paper_id,
            "paper_code": p_code,
            "attempt_id": mt.attempt_id,
            "label": mt.label,
            "score": float(mt.score),
            "max_score": float(mt.max_score),
            "score_pct": round(pct, 1),
            "taken_on": mt.taken_on.isoformat(),
            "notes": mt.notes,
        })
    return tests


@router.post("/mock-tests")
def api_create_mock_test(
    req: MockTestCreateRequest,
    session: Session = Depends(get_db),
):
    """Create a new mock test log entry."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    # Resolve paper ID
    paper = session.execute(
        sa.select(Paper).where((Paper.id == req.paper_id) | (Paper.code == req.paper_id.upper()))
    ).scalar_one_or_none()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper '{req.paper_id}' not found")

    mt = MockTest(
        user_id=user_id,
        paper_id=paper.id,
        attempt_id=req.attempt_id,
        label=req.label,
        score=req.score,
        max_score=req.max_score,
        taken_on=req.taken_on,
        notes=req.notes,
    )
    session.add(mt)
    session.commit()

    pct = (float(mt.score) / float(mt.max_score) * 100.0) if float(mt.max_score) > 0 else 0.0
    return {
        "id": mt.id,
        "paper_id": mt.paper_id,
        "paper_code": paper.code,
        "attempt_id": mt.attempt_id,
        "label": mt.label,
        "score": float(mt.score),
        "max_score": float(mt.max_score),
        "score_pct": round(pct, 1),
        "taken_on": mt.taken_on.isoformat(),
        "notes": mt.notes,
    }


@router.delete("/mock-tests/{test_id}")
def api_delete_mock_test(
    test_id: int,
    session: Session = Depends(get_db),
):
    """Delete a mock test log entry."""
    ensure_default_user(session)
    settings = get_settings()
    user_id = settings.app.user_id

    mt = session.get(MockTest, test_id)
    if not mt or mt.user_id != user_id:
        raise HTTPException(status_code=404, detail="Mock test not found")

    session.delete(mt)
    session.commit()
    return {"deleted": True, "id": test_id}


# ==============================================================================
# System Observability & Hardening Endpoints (Milestone 8)
# ==============================================================================
@router.get("/system/health")
def api_get_system_health(session: Session = Depends(get_db)):
    """Retrieve overall system health and active operational alarms."""
    from caf_common.alarms import get_system_health

    health = get_system_health(session)
    return {
        "status": health.overall_status,
        "evaluated_at": health.evaluated_at.isoformat(),
        "alarms": [
            {
                "code": a.code,
                "level": a.level,
                "message": a.message,
                "details": a.details,
            }
            for a in health.alarms
        ],
    }


@router.get("/system/backups")
def api_list_backups():
    """List existing database backup dumps with sizes and ages."""
    from caf_common.backup import list_backups

    backups = list_backups()
    return {
        "count": len(backups),
        "backups": [
            {
                "name": b["name"],
                "path": b["path"],
                "size_mb": b["size_mb"],
                "age_hours": b["age_hours"],
                "created_at": b["created_at"].isoformat(),
            }
            for b in backups
        ],
    }


@router.post("/system/backups")
def api_trigger_backup(session: Session = Depends(get_db)):
    """Trigger an immediate full database and asset backup."""
    from caf_common.backup import create_backup

    try:
        manifest = create_backup(session=session)
        return {
            "status": "ok",
            "dump_file": manifest.dump_file.name,
            "size_bytes": manifest.dump_size_bytes,
            "blobs_copied": manifest.blobs_copied,
            "configs_copied": manifest.configs_copied,
            "created_at": manifest.created_at.isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}")


@router.get("/system/model-evaluation")
def api_evaluate_models(
    threshold: float = 0.80,
    min_samples: int = 5,
    session: Session = Depends(get_db),
):
    """Evaluate classifier performance against reviewed human decisions."""
    from caf_l3.evaluate import evaluate_model_on_reviewed_decisions

    report = evaluate_model_on_reviewed_decisions(
        session=session,
        bucket_a_threshold=threshold,
        min_samples=min_samples,
    )
    return {
        "total_reviewed": report.total_reviewed,
        "top1_matches": report.top1_matches,
        "top1_agreement": report.top1_agreement,
        "bucket_metrics": {
            b: {
                "bucket": m.bucket,
                "total": m.total,
                "matched": m.matched,
                "precision": m.precision,
            }
            for b, m in report.bucket_metrics.items()
        },
        "bucket_a_threshold": report.bucket_a_threshold,
        "passed": report.passed,
        "status_note": report.status_note,
        "evaluated_at": report.evaluated_at.isoformat(),
    }

