"""Student and study tracking API routes."""

from datetime import datetime, timezone
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.app import Note, Progress, ProgressEvent, Settings, UserAccount
from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.ref import Node, Paper, WeightageMember, WeightageSection

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


class SubtopicItem(BaseModel):
    id: str
    name: str
    seq: int
    status: str
    notes: str | None = None
    first_done_at: datetime | None = None
    last_revised_at: datetime | None = None


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
                subs_out.append(
                    SubtopicItem(
                        id=s.id,
                        name=s.name,
                        seq=s.seq,
                        status=status,
                        notes=note_map.get(s.id),
                        first_done_at=pr.first_done_at if pr else None,
                        last_revised_at=pr.last_revised_at if pr else None,
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
    appearances = session.execute(
        sa.select(Appearance)
        .join(AppearanceTag, AppearanceTag.appearance_id == Appearance.id)
        .where(AppearanceTag.node_id == node_id, Appearance.status == "published")
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

    return {
        "id": subtopic.id,
        "name": subtopic.name,
        "paper": {"id": paper.id, "code": paper.code, "name": paper.name} if paper else None,
        "chapter": {"id": chapter.id, "name": chapter.name} if chapter else None,
        "topic": {"id": topic.id, "name": topic.name} if topic else None,
        "status": progress.status if progress else "not_started",
        "notes": note.body if note else None,
        "status_changed_at": progress.status_changed_at if progress else None,
        "first_done_at": progress.first_done_at if progress else None,
        "last_revised_at": progress.last_revised_at if progress else None,
        "weightage": w_info,
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

    return {
        "target_attempt": settings.app.target_attempt_id,
        "total_subtopics": total_subtopics,
        "done_subtopics": done_subtopics,
        "in_progress_subtopics": in_progress_subtopics,
        "overall_progress_pct": round(overall_pct, 1),
        "group1_progress_pct": round(g1_pct, 1),
        "group2_progress_pct": round(g2_pct, 1),
        "recent_activity": activity,
    }
