"""Test suite for Milestone 7: Depth Gate Tooling and Marginal Exam Value Evaluation."""

import uuid
from pathlib import Path
import pytest
from typer.testing import CliRunner

from caf_cli.main import app as cli_app
from caf_db.engine import get_session_factory
from caf_db.models.core import Appearance, AppearanceTag
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.intel import DepthGateReport, ScoreRun, SubtopicScore
from caf_db.models.ops import Run
from caf_db.models.ref import Attempt, Node, Paper
from caf_l5 import (
    compute_depth_gate,
    compute_ranks,
    compute_spearman_correlation,
    get_depth_gate_reports,
    load_depth_config,
    recompute_scores,
)

runner = CliRunner()


@pytest.fixture
def session():
    factory = get_session_factory()
    with factory() as sess:
        yield sess


def test_spearman_and_rank_calculations():
    """Verify ranking and Spearman rank correlation implementations."""
    # 1. Ranking
    vals = [10.0, 20.0, 20.0, 5.0]
    ranks = compute_ranks(vals, reverse=True)
    # 20.0 tied for 1st & 2nd -> 1.5, 10.0 is 3rd -> 3.0, 5.0 is 4th -> 4.0
    assert ranks == [3.0, 1.5, 1.5, 4.0]

    # 2. Perfect positive correlation
    x = [10.0, 20.0, 30.0, 40.0]
    y = [1.0, 2.0, 3.0, 4.0]
    assert compute_spearman_correlation(x, y) == 1.0

    # 3. Perfect negative correlation
    y_rev = [4.0, 3.0, 2.0, 1.0]
    assert compute_spearman_correlation(x, y_rev) == -1.0

    # 4. Partial correlation
    y_partial = [1.0, 3.0, 2.0, 4.0]
    corr = compute_spearman_correlation(x, y_partial)
    assert 0.7 <= corr < 1.0

    # 5. Degenerate cases
    assert compute_spearman_correlation([], []) == 1.0
    assert compute_spearman_correlation([5.0], [10.0]) == 1.0


def test_load_depth_config():
    """Verify loading config/depth.toml."""
    config = load_depth_config()
    assert "paper" in config
    assert "P1" in config["paper"]
    assert config["paper"]["P1"]["practice_value"] is True
    assert "P4" in config["paper"]
    assert config["paper"]["P4"]["practice_value"] is False


def test_shadow_recompute_with_provisional_appearances(session):
    """Verify that provisional items generate valid shadow scores without affecting current run."""
    # 1. Baseline run
    base_run = recompute_scores(session, shadow=False)
    assert base_run.is_current is True
    assert base_run.shadow is False

    # Find an applicable subtopic for P1
    subtopic = (
        session.query(Node)
        .filter(Node.paper_id == "s2023.P1", Node.level == "subtopic", Node.status == "active")
        .first()
    )
    assert subtopic is not None

    base_score = (
        session.query(SubtopicScore)
        .filter(SubtopicScore.score_run_id == base_run.id, SubtopicScore.node_id == subtopic.id)
        .first()
    )
    base_exam_score = base_score.exam_score if base_score else 0.0

    # 2. Create provisional appearance with substantial marks
    prov_app = Appearance(
        unit_fingerprint=f"prov_{uuid.uuid4().hex[:12]}",
        attempt_id="2024-05",
        source_paper_id="s2023.P1",
        signal_class="exam",
        marks=20,
        law_stale=False,
    )
    prov_tag = AppearanceTag(
        node_id=subtopic.id,
        share=1.0,
    )

    # 3. Shadow recompute
    shadow_run = recompute_scores(
        session,
        shadow=True,
        provisional_items=[(prov_app, prov_tag)],
    )

    assert shadow_run.shadow is True
    assert shadow_run.is_current is False

    shadow_score = (
        session.query(SubtopicScore)
        .filter(SubtopicScore.score_run_id == shadow_run.id, SubtopicScore.node_id == subtopic.id)
        .first()
    )
    assert shadow_score is not None
    assert shadow_score.exam_score > base_exam_score
    assert shadow_score.exam_count >= ((base_score.exam_count if base_score else 0) + 1)


def test_compute_depth_gate_workflow(session):
    """Verify complete Depth Gate execution with band suggestions and report persistence."""
    band_name = f"test_band_{uuid.uuid4().hex[:6]}"
    doc_sha = uuid.uuid4().hex

    # Setup synthetic pipeline run and document
    run = Run(
        stage="extract",
        status="ok",
        config_hash="m7hash",
    )
    session.add(run)
    session.flush()

    doc = Document(
        sha256=doc_sha,
        blob_path=f"/test/{doc_sha}.pdf",
        bytes=1024,
        origin="manual",
        attempt_id="2024-05",
        paper_id="s2023.P1",
        doc_type_id="suggested_answer",
        depth_band=band_name,
        catalog_status="confirmed",
        extract_status="ok",
    )
    session.add(doc)
    session.flush()

    subtopic = (
        session.query(Node)
        .filter(Node.paper_id == "s2023.P1", Node.level == "subtopic", Node.status == "active")
        .first()
    )

    unit = Unit(
        document_id=doc.id,
        extract_run_id=run.id,
        label_path="Q1(a)",
        display_label="Question 1(a)",
        kind="question",
        is_gradable=True,
        marks=10,
        page_start=1,
        page_end=1,
        block_start="p1b1",
        block_end="p1b2",
        question_text="Draft test question for depth gate",
        text_origin="ocr",
        fingerprint=uuid.uuid4().hex[:40],
        parse_confidence="high",
        current=True,
    )
    session.add(unit)
    session.flush()

    sugg = TagSuggestion(
        unit_id=unit.id,
        run_id=run.id,
        node_id=subtopic.id,
        role="primary",
        method="anchor",
        bucket="A",
        evidence={"score": 0.95},
        is_shadow=True,
    )
    session.add(sugg)
    session.commit()

    # Compute depth gate
    report = compute_depth_gate(
        session=session,
        paper="P1",
        band=band_name,
        top_k=25,
        record_report=True,
    )

    assert report.paper_code == "P1"
    assert report.band == band_name
    assert report.baseline_run_id is not None
    assert report.shadow_run_id is not None
    assert report.units_to_review == 1
    assert report.est_review_hours is not None
    assert report.jaccard is not None
    assert report.spearman is not None
    assert report.decision in ("continue", "continue_practice_value", "stop")
    assert report.decided_note is not None

    # Verify report in database
    retrieved = get_depth_gate_reports(session, paper="P1", band=band_name)
    assert len(retrieved) >= 1
    assert retrieved[0].id == report.id


def test_cli_depth_commands(session):
    """Verify caf depth gate and caf depth report CLI commands."""
    # 1. Gate command on P1
    res_gate = runner.invoke(cli_app, ["depth", "gate", "--paper", "P1", "--band", "s2017:2019", "--top-k", "10"])
    assert res_gate.exit_code == 0
    assert "Depth Gate Report" in res_gate.output
    assert "P1" in res_gate.output
    assert "Jaccard" in res_gate.output
    assert "Spearman" in res_gate.output

    # 2. Report command (now reports exist in DB)
    res_rep = runner.invoke(cli_app, ["depth", "report"])
    assert res_rep.exit_code == 0
    assert "Depth Gate Reports History" in res_rep.output


def test_depth_gate_decision_recommendation_branches(tmp_path, session):
    """Verify decision logic for continue, continue_practice_value, and stop."""
    # Write custom depth.toml
    cfg_file = tmp_path / "depth.toml"
    cfg_file.write_text("""
[paper.P1]
practice_value = true

[paper.P4]
practice_value = false
""")

    # 1. High stability (jaccard >= 0.9, new nodes < 10) on P1 (practice_value=True) -> continue_practice_value
    rep_p1 = compute_depth_gate(session, paper="P1", band="empty_band", top_k=50, record_report=False, config_path=cfg_file)
    assert rep_p1.decision == "continue_practice_value"

    # 2. High stability on P4 (practice_value=False) -> stop
    rep_p4 = compute_depth_gate(session, paper="P4", band="empty_band", top_k=50, record_report=False, config_path=cfg_file)
    assert rep_p4.decision == "stop"
