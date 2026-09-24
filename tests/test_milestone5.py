"""Test suite for Milestone 5: L5 Intelligence Engine, Scoring, Explainability, and APIs."""

import math
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa

from caf_api.main import app
from caf_db.engine import get_session_factory
from caf_db.models.intel import IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ref import Attempt, Node, Paper
from caf_l5.config import ScoringConfig, load_scoring_config
from caf_l5.scoring import (
    calculate_attributed_marks,
    compute_age_months,
    compute_decay,
    recompute_scores,
)
from caf_l5.service import (
    compute_weighted_coverage,
    get_current_score_run,
    get_subtopic_scores_for_paper,
    get_weak_subtopics,
    is_subtopic_weak,
)
from caf_l5.why import get_subtopic_why


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session():
    factory = get_session_factory()
    with factory() as sess:
        yield sess


def test_decay_and_attributed_marks_formulas():
    """Verify decay, kappa, lambda, and attributed marks mathematical correctness."""
    config = ScoringConfig(
        version="v1",
        half_life_exam_months=24.0,
        half_life_practice_months=12.0,
        p6_cross_paper_factor=0.5,
        law_stale_factor=0.5,
    )

    # 1. Decay tests
    # Age 0 -> decay 1.0
    assert compute_decay(0, config.half_life_exam_months) == 1.0
    # Age 24 with H=24 -> decay 0.5
    assert math.isclose(compute_decay(24, config.half_life_exam_months), 0.5, rel_tol=1e-5)
    # Age 48 with H=24 -> decay 0.25
    assert math.isclose(compute_decay(48, config.half_life_exam_months), 0.25, rel_tol=1e-5)
    # Practice H=12: Age 12 -> 0.5
    assert math.isclose(compute_decay(12, config.half_life_practice_months), 0.5, rel_tol=1e-5)

    # 2. Attributed marks m(a,s) = marks * share * kappa * lambda
    # Standard P1 question, active law
    m, k, lam = calculate_attributed_marks(
        marks=10,
        share=1.0,
        source_paper_id="s2023.P1",
        target_node_paper_id="s2023.P1",
        law_stale=False,
        config=config,
    )
    assert m == 10.0
    assert k == 1.0
    assert lam == 1.0

    # Secondary tag share 0.5
    m, k, lam = calculate_attributed_marks(
        marks=10,
        share=0.5,
        source_paper_id="s2023.P1",
        target_node_paper_id="s2023.P1",
        law_stale=False,
        config=config,
    )
    assert m == 5.0

    # Law stale factor λ = 0.5
    m, k, lam = calculate_attributed_marks(
        marks=10,
        share=1.0,
        source_paper_id="s2023.P4",
        target_node_paper_id="s2023.P4",
        law_stale=True,
        config=config,
    )
    assert m == 5.0
    assert lam == 0.5

    # P6 cross paper factor κ = 0.5 when source is P6 and target is P1
    m, k, lam = calculate_attributed_marks(
        marks=10,
        share=1.0,
        source_paper_id="s2023.P6",
        target_node_paper_id="s2023.P1",
        law_stale=False,
        config=config,
    )
    assert m == 5.0
    assert k == 0.5

    # P6 question tagged to P6 subtopic (not cross-paper): kappa = 1.0
    m, k, lam = calculate_attributed_marks(
        marks=10,
        share=1.0,
        source_paper_id="s2023.P6",
        target_node_paper_id="s2023.P6",
        law_stale=False,
        config=config,
    )
    assert m == 10.0
    assert k == 1.0


def test_recompute_scores_and_atomic_swap(session):
    """Test full score recomputation, normalization, and atomic score run swapping."""
    # 1. Run recompute in standard mode
    run1 = recompute_scores(session, target_attempt_id="2026-05")
    assert run1.id is not None
    assert run1.status == "ok"
    assert run1.is_current is True
    assert run1.scoring_version == "v1"

    # Verify scores and coverage were inserted
    scores = session.query(SubtopicScore).where(SubtopicScore.score_run_id == run1.id).all()
    assert len(scores) > 50

    # Importance scores must be in [0.0, 1.0]
    for s in scores:
        assert 0.0 <= s.importance <= 1.0
        assert s.freq_hits >= 0
        assert s.freq_window >= 0
        assert s.exam_score >= 0.0
        assert s.weight_prior >= 0.0

    covs = session.query(IngestionCoverage).where(IngestionCoverage.score_run_id == run1.id).all()
    assert len(covs) > 0

    # 2. Run in shadow mode
    run_shadow = recompute_scores(session, target_attempt_id="2026-05", shadow=True)
    assert run_shadow.status == "ok"
    assert run_shadow.shadow is True
    assert run_shadow.is_current is False

    # The original run1 must still remain current
    curr = session.get(ScoreRun, run1.id)
    assert curr.is_current is True

    # 3. Another standard run should atomically replace run1 as current
    run2 = recompute_scores(session, target_attempt_id="2026-05")
    assert run2.id > run1.id
    assert run2.is_current is True

    curr_old = session.get(ScoreRun, run1.id)
    assert curr_old.is_current is False


def test_subtopic_why_explainability(session):
    """Test that every number in the importance score is fully explainable."""
    current_run = get_current_score_run(session)
    if not current_run:
        current_run = recompute_scores(session)

    # Pick a subtopic with published appearances if possible, or any subtopic
    scored = session.query(SubtopicScore).filter(
        SubtopicScore.score_run_id == current_run.id,
        SubtopicScore.exam_count > 0,
    ).first()
    if not scored:
        scored = session.query(SubtopicScore).filter(
            SubtopicScore.score_run_id == current_run.id,
            SubtopicScore.applicable.is_(True),
        ).first()

    assert scored is not None
    node_id = scored.node_id

    why = get_subtopic_why(session, node_id, run_id=current_run.id)
    assert why["subtopic"]["id"] == node_id
    assert "importance_breakdown" in why
    bd = why["importance_breakdown"]

    # Verify math consistency
    expected_importance = (
        bd["weights"]["exam"] * bd["exam"]["normalized_E_hat"]
        + bd["weights"]["practice"] * bd["practice"]["normalized_P_hat"]
        + bd["weights"]["prior"] * bd["weightage_prior"]["normalized_W_hat"]
    )
    assert math.isclose(bd["importance"], round(expected_importance, 4), abs_tol=1e-3)
    assert "frequency" in why
    assert "appearances" in why
    assert isinstance(why["appearances"], list)


def test_weak_subtopic_flag_rules():
    """Verify weak flag behavior and thin data guards."""
    config = ScoringConfig(
        freq_window_attempts=5,
        weak_flag_min_hits=3,
    )

    # Case 1: Meets all conditions: applicable, freq_hits >= 3, freq_window >= 5, not_started
    assert is_subtopic_weak(
        applicable=True, freq_hits=3, freq_window=5, status="not_started", config=config
    ) is True

    # Case 2: Guard on thin data: freq_window < N (e.g. only 3 exams ingested so far)
    assert is_subtopic_weak(
        applicable=True, freq_hits=3, freq_window=4, status="not_started", config=config
    ) is False

    # Case 3: Hits < min_hits (e.g. only asked once in 5 exams)
    assert is_subtopic_weak(
        applicable=True, freq_hits=2, freq_window=5, status="not_started", config=config
    ) is False

    # Case 4: Already in progress or done
    assert is_subtopic_weak(
        applicable=True, freq_hits=4, freq_window=5, status="in_progress", config=config
    ) is False
    assert is_subtopic_weak(
        applicable=True, freq_hits=4, freq_window=5, status="done", config=config
    ) is False

    # Case 5: Inapplicable subtopic
    assert is_subtopic_weak(
        applicable=False, freq_hits=4, freq_window=5, status="not_started", config=config
    ) is False


def test_api_meta_and_tree_endpoints(client):
    """Test GET /api/v1/meta, GET /api/v1/tree, and GET /api/v1/papers/{id}/tree."""
    # 1. GET /api/v1/meta
    res_meta = client.get("/api/v1/meta")
    assert res_meta.status_code == 200
    meta = res_meta.json()
    assert meta["taxonomy_version"] == "v1"
    assert meta["scoring_version"] == "v1"
    assert meta["api_version"] == "v1"
    assert "ingestion_coverage" in meta
    assert isinstance(meta["ingestion_coverage"], list)

    # 2. GET /api/v1/tree?paper=P1
    res_tree = client.get("/api/v1/tree?paper=P1")
    assert res_tree.status_code == 200
    tree = res_tree.json()
    assert tree["code"] == "P1"
    assert len(tree["chapters"]) > 0

    first_ch = tree["chapters"][0]
    assert len(first_ch["topics"]) > 0
    first_top = first_ch["topics"][0]
    assert len(first_top["subtopics"]) > 0
    sub = first_top["subtopics"][0]
    # Check intelligence fields in tree response
    assert "importance" in sub
    assert "freq_hits" in sub
    assert "freq_window" in sub
    assert "weak" in sub
    assert "applicable" in sub

    # 3. GET /api/v1/papers/{paper_id}/tree
    res_p_tree = client.get(f"/api/v1/papers/{tree['paper_id']}/tree")
    assert res_p_tree.status_code == 200
    assert res_p_tree.json()["paper_id"] == tree["paper_id"]


def test_api_subtopic_detail_dashboard_and_why(client, session):
    """Test GET /api/v1/subtopics/{id}, GET /api/v1/dashboard, and GET /api/v1/why/subtopic/{id}."""
    current_run = get_current_score_run(session)
    if not current_run:
        current_run = recompute_scores(session)

    # Get a subtopic ID
    sub = session.query(Node).where(Node.level == "subtopic", Node.status == "active").first()
    assert sub is not None

    # 1. GET /api/v1/subtopics/{node_id}
    res_sub = client.get(f"/api/v1/subtopics/{sub.id}")
    assert res_sub.status_code == 200
    data = res_sub.json()
    assert data["id"] == sub.id
    assert "score" in data
    assert "importance" in data["score"]
    assert "exam_score" in data["score"]
    assert "weight_prior" in data["score"]
    assert "appearances" in data
    assert isinstance(data["appearances"], list)

    # 2. GET /api/v1/dashboard
    res_dash = client.get("/api/v1/dashboard")
    assert res_dash.status_code == 200
    dash = res_dash.json()
    assert "target_attempt" in dash
    assert "total_subtopics" in dash
    assert "weighted_coverage" in dash
    assert "overall_coverage_pct" in dash["weighted_coverage"]
    assert "weak_subtopics" in dash
    assert "ingestion_coverage" in dash

    # 3. GET /api/v1/why/subtopic/{node_id}
    res_why = client.get(f"/api/v1/why/subtopic/{sub.id}")
    assert res_why.status_code == 200
    why_data = res_why.json()
    assert why_data["subtopic"]["id"] == sub.id
    assert "importance_breakdown" in why_data

    # 4. POST /api/v1/curate/intel/recompute
    res_recompute = client.post("/api/v1/curate/intel/recompute")
    assert res_recompute.status_code == 200
    rec_data = res_recompute.json()
    assert rec_data["status"] == "ok"
    assert rec_data["is_current"] is True
