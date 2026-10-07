"""Phase 6 intelligence uses reviewed fixtures without live corpus approvals."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from caf_db.models.app import Progress, Settings, UserAccount
from caf_db.models.ref import Attempt
from caf_db.models.taxonomy import TaxonomyRelease, TextbookArtifact
from caf_db.models.intel import AttemptTaxonomyBinding, CorpusCoverage, RecomputeJob, ReviewedPrior, ScoreRun, SubtopicScore
from caf_db.models.questions import CorpusGeneration, PublishedQuestion, QuestionOccurrence
from caf_l5.config import ScoringConfig, load_scoring_config
from caf_l5.context import resolve_context, context_nodes
from caf_l5.jobs import claim_job, complete_job, enqueue_recompute, run_worker_once
from caf_l5.planning import generate_study_plan
from caf_l5.scoring import coverage_eligibility, normalized_component, recompute_scores, promote_score_run
from caf_l5.service import compute_weighted_coverage
from caf_l5.why import get_subtopic_why
from test_phase3_release import manifest as base_manifest
from test_phase5_publication import suggestion, review


@pytest.fixture
def manifest(tmp_path):
    value = base_manifest.__wrapped__(tmp_path)
    for artifact in value["textbook_artifacts"]:
        artifact["fallback"] = False
        artifact["target_applicability"] = "verified"
    return value


@pytest.fixture
def reviewed_context(session, suggestion):
    review(session, suggestion)
    session.commit()
    target_id = "2027-05"
    if session.get(Attempt, target_id) is None:
        session.add(Attempt(id=target_id, exam_year=2027, exam_month=5, label="May 2027"))
        session.flush()
    release = session.scalar(sa.select(TaxonomyRelease).where(
        TaxonomyRelease.taxonomy_version_id == suggestion.taxonomy_version_id))
    session.add(AttemptTaxonomyBinding(target_attempt_id=target_id,
        taxonomy_version_id=release.taxonomy_version_id, status="reviewed", reviewed_by=9,
        scoring_config=load_scoring_config().model_dump(mode="json")))
    settings = session.get(Settings, 1)
    settings.target_attempt_id = target_id
    settings.selected_paper_ids = ["s2023.P1"]
    session.commit()
    return suggestion, target_id


def complete_coverage(session, suggestion):
    row = CorpusCoverage(taxonomy_version_id=suggestion.taxonomy_version_id,
        paper_id="s2023.P1", attempt_id="2026-05", source_family="QP",
        inventory_reviewed=True, expected_slots=1, discovered_count=1, acquired_count=1,
        metadata_reviewed=True, extraction_reviewed=True, pairing_reviewed=True,
        official_scope_confirmed=True, gradable_regions_accounted=True, labels_complete=True,
        occurrence_resolved=True, reviewed_roots=1, reviewed_parts=len(suggestion.mappings),
        published_roots=1, missing_answers=1, blockers=[])
    session.add(row)
    session.commit()
    return row


def test_complete_scope_requires_evidence_not_marks_or_answers(session, reviewed_context):
    suggestion, _ = reviewed_context
    row = complete_coverage(session, suggestion)
    assert coverage_eligibility(row) == (True, [])
    row.expected_slots = None
    assert "expected_inventory_unknown" in coverage_eligibility(row)[1]
    row.expected_slots = 1
    row.gradable_regions_accounted = False
    assert "gradable_regions_unaccounted" in coverage_eligibility(row)[1]


def test_zero_observed_component_differs_from_unavailable():
    assert normalized_component(0, 0, True, .6)["normalized"] == 0
    assert normalized_component(0, 0, False, .6)["normalized"] is None
    config = load_scoring_config()
    assert ScoringConfig.model_validate(config.model_dump(mode="json")).config_hash == config.config_hash
    changed = config.model_copy(update={"secondary_share": .7, "raw_bytes": b""})
    assert changed.config_hash != config.config_hash


def test_unbound_profile_cannot_use_active_release(session, suggestion):
    context = resolve_context(session, 1)
    assert context.readiness == "taxonomy_binding_unavailable"
    assert context.run is None and context_nodes(session, context) == []
    with pytest.raises(ValueError, match="binding"):
        recompute_scores(session, "2026-05")


def test_partial_attempts_and_missing_priors_remain_unavailable(session, reviewed_context):
    suggestion, target = reviewed_context
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    node_id = suggestion.mappings[0]["primary_node_id"]
    score = session.get(SubtopicScore, (run.id, node_id))
    assert score.importance is None
    assert score.exam_score is None and score.weight_prior is None
    assert score.freq_window == 0
    why = get_subtopic_why(session, node_id, run.id, target_attempt_id=target,
                          taxonomy_version_id=suggestion.taxonomy_version_id)
    assert why["explanation_status"] == "partial_evidence"
    assert why["frequency"]["freq_hits_F"] is None
    assert why["importance_breakdown"]["weightage_prior"]["normalized_W_hat"] is None


def test_syllabus_plan_uses_real_progress_budget_and_selected_papers(session, reviewed_context):
    suggestion, _ = reviewed_context
    node_id = suggestion.mappings[0]["primary_node_id"]
    session.add(Progress(user_id=1, node_id=node_id, status="in_progress"))
    session.commit()
    plan = generate_study_plan(session, 1, hours_per_week=.9, minutes_per_subtopic=45)
    assert plan["basis"] == "syllabus"
    assert plan["items"][0]["node_id"] == node_id
    assert plan["items"][0]["status"] == "in_progress"
    assert plan["items"][0]["importance"] is None
    assert plan["allocated_minutes"] == 45 and plan["unused_minutes"] == 9
    assert {item["paper_id"] for item in plan["items"]} == {"s2023.P1"}
    coverage = compute_weighted_coverage(session, 1)
    assert coverage["basis"] == "unweighted"
    assert coverage["overall_in_progress_pct"] == 100


def test_scoped_runs_do_not_replace_other_attempt(session, reviewed_context):
    suggestion, target = reviewed_context
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    session.add(AttemptTaxonomyBinding(target_attempt_id="2026-05", taxonomy_version_id=suggestion.taxonomy_version_id,
                                     status="reviewed", reviewed_by=9, scoring_config=load_scoring_config().model_dump(mode="json")))
    session.commit()
    other = recompute_scores(session, "2026-05", taxonomy_version_id=suggestion.taxonomy_version_id)
    session.refresh(run)
    assert run.is_current and other.is_current
    assert resolve_context(session, 1).run.id == run.id


def test_pending_coalescing_expired_lease_and_owner_token(session, reviewed_context):
    suggestion, target = reviewed_context
    first = enqueue_recompute(session, target, suggestion.taxonomy_version_id)
    assert enqueue_recompute(session, target, suggestion.taxonomy_version_id).id == first.id
    claimed = claim_job(session, lease_seconds=1)
    token = claimed.lease_token
    claimed.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    reclaimed = claim_job(session)
    assert reclaimed.id == claimed.id and reclaimed.lease_token != token
    assert not complete_job(session, reclaimed.id, token, None)
    assert complete_job(session, reclaimed.id, reclaimed.lease_token, None, "fixture failure")
    assert session.get(RecomputeJob, reclaimed.id).status == "failed"


def test_older_or_stale_completion_cannot_replace_current(session, reviewed_context):
    suggestion, target = reviewed_context
    first = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    newer = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    session.refresh(first)
    assert not first.is_current
    assert not promote_score_run(session, first)
    generation = session.get(CorpusGeneration, 1)
    generation.generation += 1
    session.commit()
    assert not promote_score_run(session, newer)
    assert newer.stale


def published_fixture_copy(session, suggestion, *, signal, identity_key, aliases=None, ambiguous=False,
                           question_status="complete", unresolved_mapping=False):
    """An explicit reviewed engine fixture; never inserted into the live corpus."""
    from copy import deepcopy
    from caf_db.models.classification import ClassificationRevision, QuestionPublication
    original = session.scalar(sa.select(PublishedQuestion).where(PublishedQuestion.question_id == suggestion.question_id))
    question_id = f"isolated-{identity_key}"
    if aliases is not None:
        occurrence = session.get(QuestionOccurrence, aliases)
    else:
        occurrence = QuestionOccurrence(identity_key=identity_key, question_id=question_id,
            paper_id="s2023.P1", attempt_id="2026-05", source_family="QP" if signal == "exam" else "rtp",
            signal_class=signal, identity_status="ambiguous" if ambiguous else "confirmed",
            canonical_occurrence_id=aliases, pairing_evidence={"canonical_document_id": suggestion.document_id})
        session.add(occurrence)
    mappings = deepcopy(suggestion.mappings)
    if unresolved_mapping:
        mappings = [{**mapping, "outcome": "none_fits", "primary_node_id": None,
                     "secondary_node_ids": [], "excluded": False} for mapping in mappings]
    revision = ClassificationRevision(question_id=question_id, suggestion_revision_id=suggestion.id,
        extraction_revision_id=suggestion.extraction_revision_id, taxonomy_version_id=suggestion.taxonomy_version_id,
        mappings=mappings, context=suggestion.context, input_hash=identity_key, actor_id=9, blind=False)
    session.add(revision)
    session.flush()
    marks = deepcopy(original.marks)
    marks["issues"] = []
    for allocation in marks["allocations"]:
        allocation["allocation_status"] = "reviewed"
        allocation["choice_group"] = None
        for share in allocation["node_shares"]:
            share["attributed_marks"] = allocation["marks"] * share["share"]
    snapshot = PublishedQuestion(id=revision.id, question_id=question_id,
        extraction_revision_id=original.extraction_revision_id, taxonomy_version_id=original.taxonomy_version_id,
        occurrence_id=occurrence.id, publication_generation=original.publication_generation,
        content={**original.content, "question_id": question_id, "question_status": question_status}, mappings=mappings,
        covered_subtopics=original.covered_subtopics, marks=marks, quality=original.quality,
        source_ids=original.source_ids, assets=original.assets, search_text=original.search_text)
    session.add(snapshot)
    session.flush()
    session.add(QuestionPublication(question_id=question_id, document_id=suggestion.document_id,
        current_revision_id=revision.id, current_snapshot_id=snapshot.id))
    session.commit()
    return occurrence, snapshot


def test_full_importance_reproduces_formula_and_explanation_is_frozen(session, reviewed_context, tmp_path):
    from caf_db.models.ingest import Document
    suggestion, target = reviewed_context
    exam, _ = published_fixture_copy(session, suggestion, signal="exam", identity_key="exam")
    practice, _ = published_fixture_copy(session, suggestion, signal="practice", identity_key="practice")
    # A paired answer is the same occurrence; RTP reuse stays separate.
    published_fixture_copy(session, suggestion, signal="exam", identity_key="answer", aliases=exam.id)
    complete_coverage(session, suggestion)
    node_id = suggestion.mappings[0]["primary_node_id"]
    source = Document(sha256="f" * 64, blob_path=str(tmp_path / "official-fixture.pdf"), bytes=10,
        origin="manual", course_level="final", provenance_status="verified", scheme_id="s2023",
        paper_id="s2023.P1", doc_type_id="weightage", catalog_status="confirmed")
    session.add(source)
    session.flush()
    session.add(ReviewedPrior(taxonomy_version_id=suggestion.taxonomy_version_id, node_id=node_id,
        value=.4, reviewed_by=9, source={"kind": "official_weightage", "document_sha256": source.sha256,
            "official_url": "https://www.icai.org/isolated-official-weightage-fixture",
            "taxonomy_version_id": suggestion.taxonomy_version_id}))
    session.commit()
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    score = session.get(SubtopicScore, (run.id, node_id))
    assert score.importance == pytest.approx(1), score.evidence["components"]
    assert score.exam_count == 1 and score.practice_count >= 1
    assert score.freq_window == 1 and score.freq_hits == 1
    assert set(score.evidence["included_occurrence_ids"]) >= {exam.id, practice.id}
    before = get_subtopic_why(session, node_id, run.id, target_attempt_id=target,
                            taxonomy_version_id=suggestion.taxonomy_version_id)
    breakdown = before["importance_breakdown"]
    assert sum(breakdown[key]["weighted_contribution"] for key in
               ("exam", "practice", "weightage_prior")) == pytest.approx(score.importance)
    exam.identity_status = "ambiguous"
    session.commit()
    after = get_subtopic_why(session, node_id, run.id, target_attempt_id=target,
                           taxonomy_version_id=suggestion.taxonomy_version_id)
    assert after == before
    assert generate_study_plan(session, 1)["basis"] == "scored"


def test_unresolved_occurrence_invalidates_claimed_complete_denominator(session, reviewed_context):
    suggestion, target = reviewed_context
    published_fixture_copy(session, suggestion, signal="exam", identity_key="unresolved", ambiguous=True)
    complete_coverage(session, suggestion)
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    score = session.get(SubtopicScore, (run.id, suggestion.mappings[0]["primary_node_id"]))
    assert score.freq_window == 0 and score.exam_score is None
    assert any("published_occurrence_or_allocation_unresolved" in exclusion["reasons"]
               for exclusion in score.evidence["coverage_exclusions"])


def test_expired_unreclaimed_lease_never_promotes(session, reviewed_context):
    suggestion, target = reviewed_context
    job = enqueue_recompute(session, target, suggestion.taxonomy_version_id)
    claim_job(session)
    token = job.lease_token
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id, promote=False)
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    assert not complete_job(session, job.id, token, run.id)
    session.refresh(run)
    assert not run.is_current


def test_new_bindings_enqueue_and_worker_records_output(session, reviewed_context):
    from caf_db.engine import get_session_factory
    suggestion, target = reviewed_context
    completed = run_worker_once(get_session_factory("operations"))
    assert completed is not None
    job = session.get(RecomputeJob, completed)
    assert job.status == "ok" and job.score_run_id is not None
    context = resolve_context(session, 1)
    assert context.run.id == job.score_run_id and context.freshness["status"] == "ready"


def test_mid_compute_publication_preserves_last_same_context_and_queues_newer(session, reviewed_context, monkeypatch):
    from sqlalchemy.orm import Session
    from caf_db.engine import get_engine
    import caf_l5.scoring as scoring
    suggestion, target = reviewed_context
    previous = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    session.commit()
    session.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    original = scoring.normalized_component
    changed = False
    def mutate_during_calculation(*args):
        nonlocal changed
        if not changed:
            changed = True
            with Session(get_engine()) as publisher:
                state = publisher.get(CorpusGeneration, 1)
                state.generation += 1
                publisher.commit()
        return original(*args)
    monkeypatch.setattr(scoring, "normalized_component", mutate_during_calculation)
    stale = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    assert stale.stale and not stale.is_current
    session.refresh(previous)
    assert previous.is_current
    assert resolve_context(session, 1).run.id == previous.id
    pending = session.scalar(sa.select(RecomputeJob).where(RecomputeJob.status == "pending",
        RecomputeJob.target_attempt_id == target))
    assert pending is not None and pending.corpus_generation > stale.corpus_generation


def test_revision_scope_and_progress_are_profile_and_attempt_specific(session, reviewed_context):
    from caf_db.models.ref import ApplicabilityRule
    from caf_l5.revision import get_revision_due_list
    suggestion, _ = reviewed_context
    node_id = suggestion.mappings[0]["primary_node_id"]
    session.add(UserAccount(id=3, name="Different target profile", status="active", role="student"))
    session.flush()
    session.add(Settings(user_id=3, target_attempt_id="2026-05", selected_paper_ids=["s2023.P1"]))
    session.add(AttemptTaxonomyBinding(target_attempt_id="2026-05", taxonomy_version_id=suggestion.taxonomy_version_id,
                                      status="reviewed", reviewed_by=9, scoring_config=load_scoring_config().model_dump(mode="json")))
    old = datetime.now(timezone.utc) - timedelta(days=30)
    session.add_all([Progress(user_id=1, node_id=node_id, status="done", first_done_at=old),
                     Progress(user_id=3, node_id=node_id, status="done", first_done_at=old)])
    session.add(ApplicabilityRule(attempt_id="2026-05", node_id=node_id, effect="exclude"))
    session.commit()
    assert [item["node_id"] for item in get_revision_due_list(session, 1)] == [node_id]
    assert get_revision_due_list(session, 3) == []
    assert get_revision_due_list(session, 1)[0]["importance"] is None


def test_unknown_target_queue_request_fails_clearly(session):
    with pytest.raises(ValueError, match="Unknown target attempt"):
        enqueue_recompute(session, "2099-12")
    assert session.scalar(sa.select(sa.func.count(RecomputeJob.id))) == 0


def test_excluded_terminal_children_do_not_turn_container_into_fake_leaf(session, manifest):
    from copy import deepcopy
    from uuid import uuid4
    from caf_l0.releases import import_release
    from caf_db.models.ref import ApplicabilityRule
    from caf_l5.context import context_leaf_ids
    from caf_l5.revision import get_revision_due_list
    from test_phase3_release import authenticated_actors, review_all
    authenticated_actors(session)
    parent = next(node for node in manifest["nodes"] if node["paper_id"] == "s2023.P1" and node["kind"] == "subtopic")
    child_id = str(uuid4())
    manifest["nodes"].append({**deepcopy(parent), "id": child_id, "parent_id": parent["id"],
                              "name": "Terminal detail", "ordinal": 1})
    descriptor = next(row for row in manifest["descriptors"] if row["node_id"] == parent["id"])
    manifest["descriptors"].append({**deepcopy(descriptor), "node_id": child_id})
    manifest["heading_reconciliation"].update(expected_count=31, accounted_count=31)
    import_release(session, manifest, dry_run=False)
    review_all(session, manifest["version_id"])
    release = session.get(TaxonomyRelease, manifest["version_id"])
    release.status, release.approved_by = "active", 9
    session.add(AttemptTaxonomyBinding(target_attempt_id="2026-05", taxonomy_version_id=release.taxonomy_version_id,
        status="reviewed", reviewed_by=9, scoring_config=load_scoring_config().model_dump(mode="json")))
    session.get(Settings, 1).selected_paper_ids = ["s2023.P1"]
    session.add(ApplicabilityRule(attempt_id="2026-05", node_id=child_id, effect="exclude"))
    session.add(Progress(user_id=1, node_id=parent["id"], status="done",
                         first_done_at=datetime.now(timezone.utc) - timedelta(days=30)))
    session.commit()
    context = resolve_context(session, 1)
    assert parent["id"] in {node.id for node in context_nodes(session, context)}
    assert parent["id"] not in context_leaf_ids(session, context)
    assert child_id not in context_leaf_ids(session, context)
    plan = generate_study_plan(session, 1)
    assert plan["items"] == [] and plan["basis"] == "unavailable"
    assert compute_weighted_coverage(session, 1)["overall_coverage_pct"] is None
    assert get_revision_due_list(session, 1) == []
    run = recompute_scores(session, "2026-05", taxonomy_version_id=release.taxonomy_version_id)
    assert session.get(SubtopicScore, (run.id, parent["id"])) is None


def test_worker_lifecycle_stops_only_owned_process_and_preserves_leased_job(session, tmp_path, monkeypatch):
    import secrets
    import shutil
    import subprocess
    import time
    import worker_lifecycle
    config = load_scoring_config()
    job = RecomputeJob(target_attempt_id="2026-05", taxonomy_version_id=None,
        config_hash=config.config_hash, config_snapshot=config.model_dump(mode="json"),
        corpus_generation=0, status="running", attempts=1, lease_token="another-worker",
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=5))
    session.add(job)
    session.commit()
    monkeypatch.setattr(worker_lifecycle, "STATE_PATH", tmp_path / "worker.json")
    token = secrets.token_hex(12)
    log = tmp_path / "worker.log"
    with log.open("w") as output:
        process = subprocess.Popen([shutil.which("uv"), "run", "caf", "intel", "worker",
            "--owner-token", token], stdout=output, stderr=output)
        try:
            deadline = time.monotonic() + 10
            while "Intelligence worker started" not in log.read_text() and time.monotonic() < deadline:
                assert process.poll() is None, log.read_text()
                time.sleep(.05)
            assert "Intelligence worker started" in log.read_text(), log.read_text()
            worker_lifecycle.record_worker(process.pid, token)
            # A reused PID with an ownership mismatch is never signalled.
            original = worker_lifecycle.STATE_PATH.read_text()
            worker_lifecycle.record_worker(process.pid, "unrelated-token")
            with pytest.raises(RuntimeError, match="ownership token"):
                worker_lifecycle.stop_recorded_worker()
            assert process.poll() is None
            worker_lifecycle.STATE_PATH.write_text(original)
            assert worker_lifecycle.stop_recorded_worker()
            process.wait(timeout=10)
            assert "Intelligence worker stopped" in log.read_text(), log.read_text()
            session.refresh(job)
            assert job.status == "running" and job.lease_token == "another-worker"
            assert not worker_lifecycle.STATE_PATH.exists()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


@pytest.mark.parametrize("question_status,unresolved_mapping,reason", [
    ("partial", False, "question_scope_incomplete"),
    ("complete", True, "labels_unresolved_without_explicit_exclusion"),
])
def test_partial_content_and_unresolved_labels_cannot_enter_complete_exam_denominator(
        session, reviewed_context, question_status, unresolved_mapping, reason):
    suggestion, target = reviewed_context
    published_fixture_copy(session, suggestion, signal="exam", identity_key=reason,
        question_status=question_status, unresolved_mapping=unresolved_mapping)
    complete_coverage(session, suggestion)
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    score = session.get(SubtopicScore, (run.id, suggestion.mappings[0]["primary_node_id"]))
    assert score.freq_window == 0 and score.exam_score is None
    assert any(reason in exclusion["reasons"] for exclusion in score.evidence["coverage_exclusions"])
