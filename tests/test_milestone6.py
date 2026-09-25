"""Test suite for Milestone 6: Practice Signal, Planning Engine, Revision Queue, and Mock Tests."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa

from caf_api.main import app
from caf_db.engine import get_session_factory
from caf_db.models.app import MockTest, Progress, RevisionEvent
from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.intel import SubtopicScore
from caf_db.models.ref import Node, Paper
from caf_l2.pairing import PairedAnswer, pair_cross_doc_answers
from caf_l2.profiles import load_profile, resolve_profile
from caf_l2.segmenter import ParsedUnit
from caf_l5 import (
    generate_study_plan,
    get_revision_due_list,
    recompute_scores,
    record_revision_outcome,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session():
    factory = get_session_factory()
    with factory() as sess:
        yield sess


def test_practice_profiles_loading():
    """Verify loading and resolving profiles for RTP, MTP, and Case Scenarios."""
    profiles_dir = Path("profiles")

    # 1. RTP profile
    rtp_prof = resolve_profile(profiles_dir, scheme_id="s2023", doc_type_id="rtp")
    assert rtp_prof.doc_type == "rtp"
    assert "question_start" in rtp_prof.patterns
    assert "marks" in rtp_prof.patterns

    # 2. MTP Answer profile
    mtp_prof = resolve_profile(profiles_dir, scheme_id="s2023", doc_type_id="mtp_answer")
    assert mtp_prof.doc_type == "mtp_answer"
    assert "answer_start" in mtp_prof.patterns

    # 3. Case Scenarios profile
    cs_prof = resolve_profile(profiles_dir, scheme_id="s2023", doc_type_id="case_scenarios")
    assert cs_prof.doc_type == "case_scenarios"
    assert cs_prof.paper_max == 30


def test_cross_doc_answer_pairing():
    """Verify cross-document question and answer pairing by label_path."""
    q_units = [
        ParsedUnit(
            label_path="Q1(a)",
            display_label="1(a)",
            kind="part",
            is_gradable=True,
            marks=10,
            marks_source="explicit",
            choice_role="compulsory",
            or_group=None,
            page_start=1,
            page_end=2,
            block_start="p1-b1",
            block_end="p2-b5",
            question_lines=["Describe lease classification criteria under Ind AS 116."],
            fingerprint="q1_fp",
        ),
        ParsedUnit(
            label_path="Q1(b)",
            display_label="1(b)",
            kind="part",
            is_gradable=True,
            marks=10,
            marks_source="explicit",
            choice_role="compulsory",
            or_group=None,
            page_start=2,
            page_end=3,
            block_start="p2-b6",
            block_end="p3-b2",
            question_lines=["Calculate depreciation under Section 32."],
            fingerprint="q2_fp",
        ),
    ]

    ans_units = [
        ParsedUnit(
            label_path="Q1(a)",
            display_label="1(a)",
            kind="part",
            is_gradable=True,
            page_start=5,
            page_end=6,
            block_start="p5-b1",
            block_end="p6-b4",
            question_lines=["Suggested Answer to Q1(a):"],
            answer_lines=["A lease is classified as finance lease if substantially all risks..."],
            fingerprint="ans1_fp",
        ),
        ParsedUnit(
            label_path="Q1(b)",
            display_label="1(b)",
            kind="part",
            is_gradable=True,
            page_start=6,
            page_end=7,
            block_start="p6-b5",
            block_end="p7-b3",
            question_lines=["Answer to Q1(b):"],
            answer_lines=["Depreciation shall be calculated at 15% on block of assets..."],
            fingerprint="ans2_fp",
        ),
    ]

    paired = pair_cross_doc_answers(q_units, ans_units, answer_doc_id=99)
    assert len(paired) == 2
    assert "Q1(a)" in paired
    assert "Q1(b)" in paired

    p1 = paired["Q1(a)"]
    assert p1.pairing_method == "cross_doc"
    assert "finance lease" in p1.answer_text
    assert p1.page_start == 5
    assert p1.page_end == 6

    p2 = paired["Q1(b)"]
    assert p2.pairing_method == "cross_doc"
    assert "15%" in p2.answer_text


def test_practice_signal_scoring(session):
    """Verify that practice appearances contribute to P(s) and Importance."""
    import uuid
    # 1. Insert a synthetic practice appearance
    uid = uuid.uuid4().hex[:12]
    doc_sha = f"practice_sha_{uid}"
    app = Appearance(
        unit_fingerprint=f"prac_fp_{uid}",
        doc_sha256=doc_sha,
        attempt_id="2024-05",
        source_paper_id="s2023.P1",
        doc_type_id="rtp",
        signal_class="practice",
        display_label="RTP Q1",
        marks=12,
        gist="Practice test case on lease modifications",
        page_start=1,
        page_end=2,
        status="published",
    )
    session.add(app)
    session.flush()

    sub = session.query(Node).where(Node.paper_id == "s2023.P1", Node.level == "subtopic").first()
    assert sub is not None

    tag = AppearanceTag(
        appearance_id=app.id,
        node_id=sub.id,
        role="primary",
        share=1.0,
        decision_id=1,
    )
    session.add(tag)
    session.commit()

    # 2. Recompute scores
    run = recompute_scores(session, target_attempt_id="2026-05")
    score_rec = session.query(SubtopicScore).where(
        SubtopicScore.score_run_id == run.id,
        SubtopicScore.node_id == sub.id,
    ).first()

    assert score_rec is not None
    assert score_rec.practice_count >= 1
    assert score_rec.practice_score > 0.0


def test_next_week_planning_engine(session):
    """Verify study planning engine, budget capping, per_chapter_cap, and reason generation."""
    plan = generate_study_plan(
        session=session,
        user_id=1,
        hours_per_week=10.0,
        minutes_per_subtopic=30,
    )

    # Budget = floor(10 * 60 / 30) = 20 items
    assert plan["budget_items"] == 20
    assert plan["total_allocated"] <= 20
    items = plan["items"]
    assert len(items) > 0

    # Verify per_chapter_cap <= 3
    ch_counts = {}
    for it in items:
        ch_id = it["chapter_id"]
        ch_counts[ch_id] = ch_counts.get(ch_id, 0) + 1
        assert ch_counts[ch_id] <= 3
        # Reason must not be empty
        assert len(it["reason"]) > 0
        assert "priority_score" in it
        assert it["status"] in ("not_started", "in_progress")


def test_revision_queue_and_spaced_repetition(session):
    """Verify spaced-repetition revision queue calculation and outcome logging."""
    sub = session.query(Node).where(Node.level == "subtopic", Node.status == "active").first()
    assert sub is not None

    now = datetime.now(timezone.utc)
    # Simulate a subtopic marked done 10 days ago (first interval is 3 days -> overdue by 7 days)
    # Clean any pre-existing revision events for isolation
    session.query(RevisionEvent).where(RevisionEvent.node_id == sub.id, RevisionEvent.user_id == 1).delete()

    prog = session.get(Progress, (1, sub.id))
    if not prog:
        prog = Progress(
            user_id=1,
            node_id=sub.id,
            status="done",
            first_done_at=now - timedelta(days=10),
            last_revised_at=now - timedelta(days=10),
            status_changed_at=now - timedelta(days=10),
        )
        session.add(prog)
    else:
        prog.status = "done"
        prog.first_done_at = now - timedelta(days=10)
        prog.last_revised_at = now - timedelta(days=10)
    session.commit()

    # Check due list
    due_list = get_revision_due_list(session, user_id=1)
    matched = [d for d in due_list if d["node_id"] == sub.id]
    assert len(matched) == 1
    assert matched[0]["overdue_days"] >= 7
    assert matched[0]["revision_count_k"] == 0

    # Log 'ok' outcome
    res_ok = record_revision_outcome(session, node_id=sub.id, outcome="ok", user_id=1)
    assert res_ok["outcome"] == "ok"

    # Now with last_revised_at=today, next due is today + 7 days (interval index 1), so not due today
    due_list_after = get_revision_due_list(session, user_id=1)
    matched_after = [d for d in due_list_after if d["node_id"] == sub.id]
    assert len(matched_after) == 0

    # Test shaky outcome resets k
    record_revision_outcome(session, node_id=sub.id, outcome="shaky", user_id=1)
    # Events have outcome: ok, then shaky -> k reset to 0


def test_api_planning_revision_and_mock_tests(client, session):
    """Test /plan, /revision/due, /subtopics/{id}/revisions, /mock-tests, and dashboard."""
    # 1. GET /api/v1/plan
    res_plan = client.get("/api/v1/plan?paper=P1")
    assert res_plan.status_code == 200
    plan_data = res_plan.json()
    assert "budget_items" in plan_data
    assert "items" in plan_data

    # 2. GET /api/v1/revision/due
    res_due = client.get("/api/v1/revision/due")
    assert res_due.status_code == 200
    assert "total_due" in res_due.json()

    # 3. POST /api/v1/subtopics/{id}/revisions
    sub = session.query(Node).where(Node.level == "subtopic").first()
    res_rev = client.post(
        f"/api/v1/subtopics/{sub.id}/revisions",
        json={"outcome": "ok"},
    )
    assert res_rev.status_code == 200
    assert res_rev.json()["outcome"] == "ok"

    # 4. Mock test CRUD
    # Create
    res_mt = client.post(
        "/api/v1/mock-tests",
        json={
            "paper_id": "P1",
            "label": "MTP 2 Test",
            "score": 72.5,
            "max_score": 100.0,
            "taken_on": date.today().isoformat(),
            "notes": "Fast MCQs",
        },
    )
    assert res_mt.status_code == 200
    mt_id = res_mt.json()["id"]
    assert res_mt.json()["score_pct"] == 72.5

    # List
    res_list = client.get("/api/v1/mock-tests?paper=P1")
    assert res_list.status_code == 200
    assert any(m["id"] == mt_id for m in res_list.json())

    # Delete
    res_del = client.delete(f"/api/v1/mock-tests/{mt_id}")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # 5. GET /api/v1/dashboard includes plan_preview and revision_due_count
    res_dash = client.get("/api/v1/dashboard")
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert "plan_preview" in dash_data
    assert "revision_due_count" in dash_data
