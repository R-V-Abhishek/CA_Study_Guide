"""New-version candidates, complete-question identity and score isolation."""

from copy import deepcopy
from dataclasses import dataclass, field
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa

from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, TaxonomyGap, Unit
from caf_db.models.intel import ScoreRun, SubtopicScore
from caf_db.models.ops import Run
from caf_db.models.ref import Node
from caf_db.models.taxonomy import TaxonomyRelease
from caf_l0.hierarchy import descendant_leaves, leaf_scope, version_nodes
from caf_l0.releases import activate_release, approve_release, eligible_candidates, import_release
from caf_l1.catalog import confirm_document
from caf_l1.infer import infer_metadata
from caf_l3.llm import GeminiClassifier
from caf_l3.pipeline import ClassificationPipeline
from caf_l3.textbook import NeedsTaxonomyReview, TextbookClassifier
from caf_l5.scoring import recompute_scores
from caf_l5.service import get_current_score_run
from test_phase3_release import authenticated_actors, manifest, review_all


def prepare(session, manifest, *, review=True, activate=False):
    authenticated_actors(session)
    import_release(session, manifest, dry_run=False)
    if review:
        review_all(session, manifest["version_id"])
    release = session.get(TaxonomyRelease, manifest["version_id"])
    if activate:
        approve_release(session, release.version_id, release.manifest_hash, 9)
        activate_release(session, release.version_id, release.manifest_hash, dry_run=False)
    session.commit()
    return release


def document(session, *, course="final", provenance="verified", doc_type="rtp"):
    doc = Document(sha256=uuid4().hex + uuid4().hex, blob_path="/fixture.pdf", bytes=100,
        origin="manual", scheme_id="s2023", paper_id="s2023.P1", attempt_id="2026-01",
        doc_type_id=doc_type, course_level=course, provenance_status=provenance,
        title="Deterministic source fixture", catalog_status="confirmed", extract_status="ok")
    session.add(doc)
    session.flush()
    return doc


def unit(session, doc, text, *, parent=None, label="Q1.a", gradable=True):
    item = Unit(document_id=doc.id, extract_run_id=1, parent_unit_id=parent,
        label_path=label, display_label=label, kind="part" if parent else "question",
        is_gradable=gradable, marks=10, marks_source="explicit", page_start=1, page_end=1,
        block_start="p1-b1", block_end="p1-b2", question_text=text, text_origin="pdf",
        fingerprint=uuid4().hex, parse_confidence="high", classify_status="pending", current=True)
    session.add(item)
    session.flush()
    return item


def test_new_candidates_require_review_and_do_not_leak_into_legacy(session, manifest):
    old_ids = {node.id for node in version_nodes(session)}
    release = prepare(session, manifest, review=False)
    assert {node.id for node in version_nodes(session)} == old_ids
    session.commit()
    from caf_common.audit import collect_baseline
    audit = collect_baseline(session.get_bind())
    completeness = audit["taxonomy_completeness"]
    assert completeness["scope"] == "legacy"
    assert sum(row["count"] for row in completeness["nodes_by_paper_level"]) == len(old_ids)
    assert all(row["node_id"] in old_ids for row in completeness["subtopics_missing_descriptors"])
    assert completeness["textbook_releases"][0]["node_count"] == 30
    assert completeness["textbook_releases"][0]["descriptor_revision_count"] == 6
    assert completeness["textbook_releases"][0]["recorded_descriptor_approval_count"] == 0
    unresolved = TextbookClassifier(session, release.version_id).classify_unit("s2023.P1", "discounting")
    assert unresolved.outcome == 'needs_review' and unresolved.primary_node_id is None
    review_all(session, release.version_id)
    result = TextbookClassifier(session, release.version_id).classify_unit("s2023.P1", "discounting", use_llm=False)
    assert result.primary_node_id not in old_ids
    assert result.evidence["taxonomy_version_id"] == release.taxonomy_version_id
    assert [node["level"] for node in result.evidence["breadcrumbs"][result.primary_node_id]] == [
        "module", "chapter", "unit", "topic", "subtopic"]
    no_fit = TextbookClassifier(session, release.version_id).classify_unit("s2023.P1", "unrelated medical question", use_llm=False)
    assert no_fit.outcome == 'none_fits' and no_fit.primary_node_id is None


def test_recursive_classification_counts_exclude_subtopic_containers(session, manifest):
    parent = manifest["nodes"][4]
    child = deepcopy(parent)
    child.update(id=str(uuid4()), parent_id=parent["id"], name="Terminal concept")
    manifest["nodes"].append(child)
    descriptor = deepcopy(manifest["descriptors"][0])
    descriptor["node_id"] = child["id"]
    manifest["descriptors"].append(descriptor)
    release = prepare(session, manifest, activate=True)
    ids = set(session.scalars(sa.select(Node.id).where(leaf_scope(session))))
    assert child["id"] in ids and parent["id"] not in ids and len(ids) == 6
    assert {n.node_id for n in eligible_candidates(session, release.taxonomy_version_id)} == ids
    nodes = {n.id: n for n in version_nodes(session)}
    assert descendant_leaves(parent["id"], nodes) == [child["id"]]


def test_multi_subtopic_and_explicit_ibs_references(session, manifest):
    first = manifest["nodes"][4]
    second = deepcopy(first)
    second["id"] = str(uuid4())
    second["name"] = "Capital budgeting"
    second["ordinal"] += 1
    manifest["nodes"].append(second)
    descriptor = deepcopy(manifest["descriptors"][0])
    descriptor["node_id"] = second["id"]
    descriptor["terminology"] = ["net present value"]
    manifest["descriptors"].append(descriptor)
    release = prepare(session, manifest)
    classifier = TextbookClassifier(session, release.version_id)
    result = classifier.classify_unit("s2023.P1", "Calculate net present value using discounting", use_llm=False)
    assert result.outcome == "needs_review" and result.primary_node_id is None
    assert set(result.alternatives) == {first["id"], second["id"]}
    assert not result.secondary_node_ids
    integrated = classifier.classify_unit("s2023.P6", "Calculate net present value", use_llm=False)
    assert integrated.evidence["cross_paper_references"] == [second["id"]]
    prompt, candidates = GeminiClassifier(session, taxonomy_version_id=release.taxonomy_version_id).build_candidate_prompt("s2023.P6")
    assert second["id"] in candidates and "module 1" in prompt and "Descriptor revision" in prompt
    assert all(candidate.level == "subtopic" for candidate in candidates.values())


@dataclass
class ProviderResponse:
    text: str
    usage_metadata: None = None


@dataclass
class ProviderModels:
    result: dict
    calls: list[str] = field(default_factory=list)

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        if model == "unavailable-model":
            raise RuntimeError("Deterministic unavailable provider fixture")
        return ProviderResponse(json.dumps(self.result))


@dataclass
class ProviderClient:
    models: ProviderModels


@pytest.mark.parametrize("candidate", ["", "legacy-node-id", "reviewed"])
def test_llm_rejects_forced_candidates_and_records_successful_model(session, manifest, candidate):
    release = prepare(session, manifest)
    node_id = manifest["descriptors"][0]["node_id"] if candidate == "reviewed" else candidate
    classifier = GeminiClassifier(session, taxonomy_version_id=release.taxonomy_version_id)
    classifier.api_key = "deterministic-test-provider"
    provider = ProviderModels(dict(primary_node_id=node_id, confidence=0.9, bucket="A",
        core_tested_concept="discounting", justification="Reviewed descriptor evidence", gist="Discount cash flows"))
    classifier.client = ProviderClient(provider)
    classifier.model_candidates = ["unavailable-model", "fixture-successful-model"]
    if candidate == "reviewed":
        result = classifier.classify_unit("s2023.P1", "discounting", retries=0)
        assert result.model_id == "fixture-successful-model"
    else:
        with pytest.raises(NeedsTaxonomyReview, match="unsupported candidate"):
            classifier.classify_unit("s2023.P1", "discounting", retries=0)
    assert provider.calls == ["unavailable-model", "fixture-successful-model"]


@pytest.mark.parametrize("doc_type", ["rtp", "mtp_question", "model_question"])
def test_pipeline_preserves_root_and_historical_decision(session, manifest, doc_type):
    release = prepare(session, manifest)
    doc = document(session, doc_type=doc_type)
    if doc_type == "model_question":
        doc.attempt_id = None
    root = unit(session, doc, "Use discounting for the following calculations", label="Q1", gradable=False)
    part = unit(session, doc, "Calculate the cash-flow value", parent=root.id)
    second_part = unit(session, doc, "Calculate another cash-flow value", parent=root.id, label="Q1.b")
    decision = Decision(unit_fingerprint=part.fingerprint, action="accept", payload={"historical": True})
    session.add(decision)
    run = Run(stage="l3_classify", status="running", stats={})
    session.add(run)
    session.commit()
    summary = ClassificationPipeline(session, version_id=release.version_id).run_classification(run.id, doc_id=doc.id, use_llm=False, limit=1)
    assert summary.primary_suggestions == 1
    suggestion = session.scalar(sa.select(TagSuggestion).where(TagSuggestion.unit_id == part.id))
    assert suggestion.taxonomy_version_id == release.taxonomy_version_id
    assert suggestion.descriptor_revision_id is not None
    assert suggestion.evidence["main_question_id"] == root.id
    assert suggestion.evidence["part_label"] == "Q1.a"
    assert suggestion.evidence["source_document_sha256"] == doc.sha256
    assert session.get(Decision, decision.id).payload == {"historical": True}
    assert run.taxonomy_version_id == release.taxonomy_version_id
    repeated = ClassificationPipeline(session, version_id=release.version_id).run_classification(run.id, doc_id=doc.id, use_llm=False)
    assert repeated.total_processed == 1
    assert session.scalar(sa.select(TagSuggestion).where(TagSuggestion.unit_id == second_part.id)) is not None
    repeated = ClassificationPipeline(session, version_id=release.version_id).run_classification(run.id, doc_id=doc.id, use_llm=False)
    assert repeated.total_processed == 0
    from caf_l4.publish import make_decision
    with pytest.raises(ValueError, match="complete root"):
        make_decision(session, part.id, "accept", {"primary_node_id": suggestion.node_id})
    assert session.get(Decision, decision.id).payload == {"historical": True}


def test_queue_excludes_lower_level_synthetic_and_unresolved(session, manifest):
    release = prepare(session, manifest)
    for course, provenance in [("foundation", "verified"), ("intermediate", "verified"),
                               ("final", "synthetic"), ("final", "unresolved")]:
        doc = document(session, course=course, provenance=provenance)
        unit(session, doc, "discounting")
    for doc_type in ("study_material", "model_answer"):
        doc = document(session, doc_type=doc_type)
        unit(session, doc, "discounting")
    run = Run(stage="l3_classify", status="running", stats={})
    session.add(run)
    session.commit()
    summary = ClassificationPipeline(session, version_id=release.version_id).run_classification(run.id, use_llm=False)
    assert summary.total_processed == 0
    assert session.scalar(sa.select(sa.func.count()).select_from(TagSuggestion)) == 0


@pytest.mark.parametrize("shadow", [False, True])
def test_no_fit_records_taxonomy_review_gap(session, manifest, shadow):
    release = prepare(session, manifest)
    doc = document(session)
    item = unit(session, doc, "unsupported concept")
    supported = unit(session, doc, "discounting", label="Q2")
    session.commit()
    pipeline = ClassificationPipeline(session, version_id=release.version_id)
    pipeline.run_classification(1, doc_id=doc.id, use_llm=False, limit=1, is_shadow=shadow)
    assert item.classify_status == ("pending" if shadow else "needs_review")
    assert session.scalar(sa.select(TaxonomyGap).where(TaxonomyGap.unit_id == item.id)) is not None
    assert session.scalar(sa.select(TagSuggestion).where(TagSuggestion.unit_id == item.id)) is None
    resumed = pipeline.run_classification(1, doc_id=doc.id, use_llm=False, limit=1, is_shadow=shadow)
    assert resumed.primary_suggestions == 1
    assert session.scalar(sa.select(TagSuggestion).where(TagSuggestion.unit_id == supported.id)) is not None
    assert session.scalar(sa.select(sa.func.count()).select_from(TaxonomyGap)) == 1


def test_provider_failure_is_not_reported_as_success(session, manifest, monkeypatch):
    release = prepare(session, manifest)
    doc = document(session)
    item = unit(session, doc, "discounting")
    session.commit()
    pipeline = ClassificationPipeline(session, version_id=release.version_id)

    def unavailable_provider(**kwargs):
        raise RuntimeError("Deterministic provider outage")

    monkeypatch.setattr(pipeline.classifier, "classify_unit", unavailable_provider)
    summary = pipeline.run_classification(1, doc_id=doc.id)
    assert summary.is_partial and summary.failed_units == 1 and summary.total_processed == 0
    assert "failed and need retry" in summary.status_message
    assert item.classify_status == "failed"
    assert session.get(Run, 1).taxonomy_version_id == release.taxonomy_version_id


def test_evaluation_requires_decisions_against_the_same_taxonomy(session, manifest):
    from caf_l3.evaluate import evaluate_model_on_reviewed_decisions
    from caf_l3.benchmark import BENCHMARK_FLAG, evaluate_calibration_benchmark
    release = prepare(session, manifest, activate=True)
    doc = document(session)
    item = unit(session, doc, "discounting")
    item.validation_flags = [BENCHMARK_FLAG]
    session.commit()
    ClassificationPipeline(session).run_classification(1, doc_id=doc.id, use_llm=False)
    accepted_id = manifest["nodes"][4]["id"]
    historical = Decision(unit_fingerprint=item.fingerprint, action="accept",
        payload={"primary_node_id": accepted_id}, blind=False)
    session.add(historical)
    session.commit()
    report = evaluate_model_on_reviewed_decisions(session, min_samples=1)
    assert report.total_reviewed == 0 and not report.passed
    assert evaluate_calibration_benchmark(session).total_decided == 0
    session.add(Decision(unit_fingerprint=item.fingerprint, action="accept", blind=False,
        payload={"primary_node_id": accepted_id, "taxonomy_version_id": release.taxonomy_version_id}))
    session.commit()
    report = evaluate_model_on_reviewed_decisions(session, min_samples=1)
    assert report.total_reviewed == 0  # Version alone does not freeze suggestion/content evidence.
    assert not report.passed  # A keyword suggestion supplies no Bucket A evidence.
    assert evaluate_calibration_benchmark(session).total_decided == 0
    assert session.get(Decision, historical.id).payload == {"primary_node_id": accepted_id}


def test_attempt_version_scores_and_recursive_leaves(session, manifest):
    old_run = recompute_scores(session, target_attempt_id="2027-05")
    assert get_current_score_run(session, "2027-05").id == old_run.id
    release = prepare(session, manifest, activate=True)
    assert get_current_score_run(session, "2027-05") is None
    nodes = {node.id: node for node in version_nodes(session)}
    assert len(nodes) == 30
    assert descendant_leaves(manifest["nodes"][0]["id"], nodes) == [manifest["nodes"][4]["id"]]
    from caf_api.auth import Principal
    from caf_api.routes import get_paper_tree
    paper_tree = get_paper_tree("s2023.P1", session,
        Principal(id=1, name="Fixture student", email=None, role="student", status="active"))
    assert paper_tree["chapters"][0].total_subtopics == 1
    assert paper_tree["chapters"][0].topics[0].subtopics[0].id == manifest["nodes"][4]["id"]
    assert paper_tree["hierarchy"][0]["children"][0]["children"][0]["level"] == "unit"
    run = recompute_scores(session, target_attempt_id="2027-05")
    assert run.taxonomy_version_id == release.taxonomy_version_id
    assert get_current_score_run(session, "2026-01") is None
    scores = list(session.scalars(sa.select(SubtopicScore).where(SubtopicScore.score_run_id == run.id)))
    assert len(scores) == 6
    assert all(score.weight_prior == 0 and score.importance == 0 for score in scores)
    from caf_l5.why import get_subtopic_why
    explanation = get_subtopic_why(session, manifest["nodes"][4]["id"], target_attempt_id="2027-05")
    prior = explanation["importance_breakdown"]["weightage_prior"]
    assert prior["available"] is False and "configured weights are unchanged" in prior["unavailable_reason"]
    assert session.get(ScoreRun, old_run.id) is not None


def test_model_mock_course_and_nullable_attempt_metadata(session):
    model = infer_metadata("https://resource.cdn.icai.org/model.pdf",
        anchor_text="Paper 1 Model Test Paper Question Paper", breadcrumb=["Final"])
    mock = infer_metadata("https://resource.cdn.icai.org/mock.pdf",
        anchor_text="May 2026 Paper 1 Mock Test Paper Question Paper Series II", breadcrumb=["Final"])
    lower = infer_metadata("https://resource.cdn.icai.org/foundation.pdf",
        anchor_text="Paper 1 Model Test Paper", breadcrumb=["Foundation"])
    assert model["doc_type_id"] == "model_question" and model["attempt_id"] is None
    assert model["catalog_status"] == "inferred"
    assert mock["doc_type_id"] == "mtp_question" and mock["attempt_id"] == "2026-05"
    assert mock["series"] == "2"
    assert lower["course_level"] == "foundation" and lower["paper_id"] is None
    doc = document(session, doc_type="model_question")
    doc.attempt_id = None
    assert confirm_document(session, doc.id).attempt_id is None
