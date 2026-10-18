"""Frozen corpus adoption authorizes pinned inputs without inventing student review."""

from copy import deepcopy

import pytest
import sqlalchemy as sa

from caf_db.models.app import Note, Progress, Settings
from caf_db.models.classification import (
    BaselineAdoption, CandidateCatalog, ClassificationRevision,
    ClassificationVerification, QuestionPublication, SuggestionRevision,
)
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.taxonomy import DescriptorRevision, TaxonomyRelease, TextbookArtifact
from caf_l0.releases import approve_descriptor, artifact_context
from caf_l2.revisions import digest
from caf_l4.baseline import activate_baseline, prepare_baseline, rollback_baseline
from caf_l4.revisions import readiness, review_classification
from caf_l5.context import context_nodes, resolve_context
from test_phase3_release import manifest
from test_phase5_publication import suggestion


@pytest.fixture
def frozen(session, suggestion):
    """Use real extracted source evidence; retain its older inline suggestion."""
    document = session.get(Document, suggestion.document_id)
    extraction = session.get(ExtractionRevision, suggestion.extraction_revision_id)
    catalog = deepcopy(suggestion.candidates)
    catalog_hash = digest(catalog)
    record = dict(question_id=suggestion.question_id, document_id=document.id,
        document_sha256=document.sha256, extraction_revision_id=extraction.id,
        extraction_digest=extraction.content_digest, context=deepcopy(suggestion.context),
        input_hash=suggestion.input_hash, original_input_hash=suggestion.input_hash,
        catalog_hash=catalog_hash, mappings=deepcopy(suggestion.mappings),
        saved=True, execution={"method": "saved-fixture"}, pack="fixture-final",
        result_hash=digest(suggestion.mappings))
    metadata = dict(release_id="baseline-fixture", target_attempt="2027-05",
        counts=dict(roots=1, parts=len(record["mappings"]), catalog_nodes=len({
            node["id"] for candidate in catalog for node in candidate["path"]})),
        catalog_hashes=[catalog_hash])
    return dict(release_id=metadata["release_id"], target_attempt="2027-05",
        manifest_hash=digest(metadata), manifest=metadata, catalogs={catalog_hash: catalog},
        records=[record])


def adopted_suggestion(session, adoption):
    release = session.get(TaxonomyRelease, adoption.release_id)
    return session.scalar(sa.select(SuggestionRevision).where(
        SuggestionRevision.taxonomy_version_id == release.taxonomy_version_id))


def activate(session, frozen):
    result = activate_baseline(session, frozen["release_id"], frozen["manifest_hash"], 9)
    session.flush()
    return result


def test_adoption_requires_active_administrator(session, frozen):
    with pytest.raises(ValueError, match="administrator"):
        prepare_baseline(session, frozen, 1)
    assert session.get(BaselineAdoption, frozen["release_id"]) is None
    prepare_baseline(session, frozen, 9)
    session.commit()
    for operation in (activate_baseline, rollback_baseline):
        with pytest.raises(ValueError, match="administrator"):
            operation(session, frozen["release_id"], frozen["manifest_hash"], 1)
        session.rollback()


def test_prepare_retry_preserves_older_suggestions_without_verifications(session, frozen, suggestion):
    original = deepcopy(suggestion.candidates)
    first = prepare_baseline(session, frozen, 9)
    session.commit()
    new = adopted_suggestion(session, first)
    assert first.status == "prepared"
    assert not readiness(session, new)["eligible"]
    assert "baseline_not_authorized" in readiness(session, new)["blockers"]
    assert new.id != suggestion.id
    assert new.candidates == [] and new.candidate_catalog_hash
    assert session.get(CandidateCatalog, new.candidate_catalog_hash) is not None
    second = prepare_baseline(session, deepcopy(frozen), 9)
    session.commit()
    assert second.release_id == first.release_id
    assert session.scalar(sa.select(sa.func.count()).select_from(SuggestionRevision)) == 2
    assert session.get(SuggestionRevision, suggestion.id).candidates == original
    assert session.scalar(sa.select(sa.func.count()).select_from(ClassificationVerification)) == 0
    assert session.scalar(sa.select(sa.func.count()).select_from(ClassificationRevision)) == 0


def test_preparation_can_be_interrupted_and_retried(session, frozen):
    prepare_baseline(session, frozen, 9)
    session.rollback()
    assert session.get(BaselineAdoption, frozen["release_id"]) is None
    assert session.get(TaxonomyRelease, frozen["release_id"]) is None
    assert session.scalar(sa.select(sa.func.count()).select_from(SuggestionRevision)) == 1
    prepare_baseline(session, frozen, 9)
    session.commit()
    assert session.get(BaselineAdoption, frozen["release_id"]).status == "prepared"


def test_conflicting_frozen_inputs_cannot_activate(session, frozen):
    prepare_baseline(session, frozen, 9)
    session.commit()
    conflicting = deepcopy(frozen)
    conflicting["manifest_hash"] = "0" * 64
    with pytest.raises(ValueError):
        prepare_baseline(session, conflicting, 9)
    session.rollback()
    with pytest.raises(ValueError):
        activate_baseline(session, frozen["release_id"], "0" * 64, 9)
    session.rollback()
    conflicting = deepcopy(frozen)
    conflicting["records"][0]["mappings"] = []
    with pytest.raises(ValueError):
        prepare_baseline(session, conflicting, 9)
    session.rollback()
    assert session.get(BaselineAdoption, frozen["release_id"]).status == "prepared"
    assert session.scalar(sa.select(sa.func.count()).select_from(QuestionPublication)) == 0


def test_incomplete_mapping_cannot_be_adopted(session, frozen):
    invalid = deepcopy(frozen)
    invalid["records"][0]["mappings"] = invalid["records"][0]["mappings"][:1]
    with pytest.raises(ValueError, match="part|mapping|complete"):
        prepare_baseline(session, invalid, 9)
        activate(session, invalid)
    session.rollback()
    assert session.get(BaselineAdoption, frozen["release_id"]) is None
    assert session.scalar(sa.select(sa.func.count()).select_from(QuestionPublication)) == 0


def test_unresolved_parts_stay_published_without_invented_labels(session, frozen):
    record = frozen["records"][0]
    record["mappings"] = [{**mapping, "outcome": outcome, "primary_node_id": None,
        "secondary_node_ids": [], "evidence": {}, "confidence": None, "bucket": None}
        for mapping, outcome in zip(record["mappings"], ["needs_review", "none_fits"], strict=True)]
    record["result_hash"] = digest(record["mappings"])
    adoption = prepare_baseline(session, frozen, 9)
    activate(session, frozen)
    session.commit()
    imported = adopted_suggestion(session, adoption)
    publication = session.get(QuestionPublication, imported.question_id)
    assert publication.current_snapshot_id is not None
    revision = session.get(ClassificationRevision, publication.current_revision_id)
    assert [mapping["outcome"] for mapping in revision.mappings] == ["needs_review", "none_fits"]
    assert all(mapping["primary_node_id"] is None for mapping in revision.mappings)
    assert revision.context["answer_status"] == "missing"
    assert session.scalar(sa.select(sa.func.count()).select_from(ClassificationVerification)) == 0


def test_real_role_api_activation_shared_candidate_review_and_reader(
    session, frozen, authenticated_client, monkeypatch,
):
    monkeypatch.setattr("caf_l3.baseline_pack.freeze_pack", lambda directory: frozen)
    student = authenticated_client(user_id=1, role="student")
    admin = authenticated_client(user_id=9, role="administrator")
    assert student.post("/api/v1/curate/baselines/prepare").status_code == 403
    prepared = admin.post("/api/v1/curate/baselines/prepare")
    assert prepared.status_code == 200, prepared.text
    endpoint = f"/api/v1/curate/baselines/{frozen['release_id']}/activate"
    body = {"manifest_hash": frozen["manifest_hash"]}
    assert student.post(endpoint, json=body).status_code == 403
    activated = admin.post(endpoint, json=body)
    assert activated.status_code == 200, activated.text
    question_id = frozen["records"][0]["question_id"]
    queue = student.get("/api/v1/curate/classifications", params={"question_id": question_id})
    assert queue.status_code == 200, queue.text
    item = queue.json()[0]
    assert item["candidates"] == []
    assert item["candidate_catalog_hash"] == next(iter(frozen["catalogs"]))
    catalog = student.get(f"/api/v1/curate/candidate-catalogs/{item['candidate_catalog_hash']}")
    assert catalog.status_code == 200, catalog.text
    assert catalog.json() == next(iter(frozen["catalogs"].values()))
    assert item["provenance"]["baseline_release_id"] == frozen["release_id"]
    assert item["publication_ready"] and item["verification_count"] == 0
    reader = student.get(f"/api/v1/questions/{question_id}")
    assert reader.status_code == 200, reader.text
    assert reader.json()["verification_count"] == 0
    assert reader.json()["content"]["answer_status"] == "missing"
    changed = [{**mapping, "outcome": "none_fits", "primary_node_id": None,
        "secondary_node_ids": [], "evidence": {}} for mapping in item["mappings"]]
    correction = admin.post(
        f"/api/v1/curate/classifications/{item['suggestion_revision_id']}/review",
        json=dict(mappings=changed, note="Reviewed source after baseline adoption",
            expected_suggestion_revision_id=item["suggestion_revision_id"],
            expected_publication_revision_id=item["publication_revision_id"],
            idempotency_key="api-baseline-correction"),
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["current_revision_id"] != item["publication_revision_id"]


def test_activation_is_transactional_and_idempotent_without_fake_verifications(session, frozen):
    adoption = prepare_baseline(session, frozen, 9)
    session.commit()
    old_target = session.get(Settings, 1).target_attempt_id
    activate(session, frozen)
    session.rollback()
    assert session.get(BaselineAdoption, adoption.release_id).status == "prepared"
    assert session.get(Settings, 1).target_attempt_id == old_target
    assert session.scalar(sa.select(sa.func.count()).select_from(QuestionPublication)) == 0
    activate(session, frozen)
    session.commit()
    revision_ids = list(session.scalars(sa.select(ClassificationRevision.id)))
    assert len(revision_ids) == 1
    activate(session, frozen)
    session.commit()
    assert list(session.scalars(sa.select(ClassificationRevision.id))) == revision_ids
    assert session.scalar(sa.select(sa.func.count()).select_from(ClassificationVerification)) == 0
    assert session.get(BaselineAdoption, adoption.release_id).status == "active"


@pytest.mark.parametrize("change", ["source", "source_metadata", "extraction", "descriptor", "catalog"])
def test_adoption_authorization_does_not_cover_changed_inputs(session, frozen, change):
    adoption = prepare_baseline(session, frozen, 9)
    activate(session, frozen)
    session.commit()
    imported = adopted_suggestion(session, adoption)
    assert readiness(session, imported)["eligible"], readiness(session, imported)
    if change == "source":
        document = session.get(Document, imported.document_id)
        document.sha256 = "f" * 64
    elif change == "source_metadata":
        document = session.get(Document, imported.document_id)
        document.catalog_status = "needs_curation"
    elif change == "extraction":
        document = session.get(Document, imported.document_id)
        document.current_revision_id = None
    elif change == "catalog":
        catalog = session.get(CandidateCatalog, imported.candidate_catalog_hash)
        changed = deepcopy(catalog.candidates)
        changed[0]["descriptor"]["definition"] = "Evidence changed after adoption"
        catalog.candidates = changed
    else:
        pinned = session.scalar(sa.select(DescriptorRevision).where(
            DescriptorRevision.taxonomy_version_id == imported.taxonomy_version_id))
        session.add(DescriptorRevision(node_id=pinned.node_id,
            taxonomy_version_id=pinned.taxonomy_version_id, revision=pinned.revision + 1,
            content={**pinned.content, "definition": "Changed after adoption"},
            content_hash=digest({**pinned.content, "definition": "Changed after adoption"})))
    session.flush()
    assert not readiness(session, imported)["eligible"]


def test_copy_of_adopted_suggestion_cannot_inherit_authorization(session, frozen):
    adoption = prepare_baseline(session, frozen, 9)
    activate(session, frozen)
    session.commit()
    imported = adopted_suggestion(session, adoption)
    copied = SuggestionRevision(batch_key="forged-baseline-copy", input_hash=imported.input_hash,
        document_id=imported.document_id, extraction_revision_id=imported.extraction_revision_id,
        question_id=imported.question_id, taxonomy_version_id=imported.taxonomy_version_id,
        run_id=imported.run_id, experimental=False, context=deepcopy(imported.context),
        candidates=[], candidate_catalog_hash=imported.candidate_catalog_hash,
        mappings=deepcopy(imported.mappings), provenance=deepcopy(imported.provenance))
    session.add(copied)
    session.flush()
    gate = readiness(session, copied)
    assert not gate["eligible"]
    assert "stale_baseline_inputs" in gate["blockers"]
    publication = session.get(QuestionPublication, imported.question_id)
    with pytest.raises(ValueError, match="stale_baseline_inputs"):
        review_classification(session, copied.id, 9, copied.mappings, copied.id,
            publication.current_revision_id, "forged-baseline-review", note="Attempted copied authorization")
    session.rollback()


def test_index_artifact_metadata_preserves_evidence_without_claiming_applicability():
    original = dict(heading_origin="module_index", download_url="https://example.invalid/index.pdf",
        source_context="Original module index headings", fallback=True,
        target_applicability="unresolved", headings=["Recognition criteria"])
    artifact = TextbookArtifact(taxonomy_version_id=123, id="older-module-index",
        paper_id="s2023.P5", course_level="Final", edition="Older edition",
        availability="verified", sha256="a" * 64, page_count=2,
        metadata_json=deepcopy(original))
    presented = artifact_context(artifact)
    assert presented["applicable_attempts"] == []
    assert presented["landing_url"] == ""
    assert presented["heading_reconciliation"]["status"] == "pending"
    assert presented["heading_reconciliation"]["unresolved"]
    assert presented["paper_id"] == "s2023.P5"
    assert presented["target_applicability"] == "unresolved"
    assert presented["headings"] == original["headings"]
    assert artifact.metadata_json == original


def test_raw_index_heading_descriptor_requires_authored_revision_before_approval(session, frozen):
    adoption = prepare_baseline(session, frozen, 9)
    session.commit()
    release = session.get(TaxonomyRelease, adoption.release_id)
    original = session.scalar(sa.select(DescriptorRevision).where(
        DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id))
    raw = dict(status="index_derived_draft_requires_review", definition="Index heading evidence only",
        source_heading="Recognition criteria", terminology=["Recognition criteria"])
    revision = DescriptorRevision(taxonomy_version_id=release.taxonomy_version_id,
        node_id=original.node_id, revision=original.revision + 1,
        content=raw, content_hash=digest(raw))
    session.add(revision)
    session.commit()
    with pytest.raises(ValueError, match="authored textbook descriptor"):
        approve_descriptor(session, release.version_id, revision.node_id, revision.revision, 9)
    session.rollback()


def test_unresolved_older_sources_are_available_for_study_without_authoritative_scoring(session, frozen):
    adoption = prepare_baseline(session, frozen, 9)
    activate(session, frozen)
    session.commit()
    imported = adopted_suggestion(session, adoption)
    node_id = imported.mappings[0]["primary_node_id"]
    context = resolve_context(session, 1)
    assert context.readiness == "ready"
    assert node_id in context.unresolved_node_ids
    assert node_id in {node.id for node in context_nodes(session, context, study=True)}
    assert node_id not in {node.id for node in context_nodes(session, context)}


def test_rollback_preserves_personal_records_and_subsequent_corrections(session, frozen):
    adoption = prepare_baseline(session, frozen, 9)
    activate(session, frozen)
    session.commit()
    imported = adopted_suggestion(session, adoption)
    publication = session.get(QuestionPublication, imported.question_id)
    baseline_revision = publication.current_revision_id
    node_id = imported.mappings[0]["primary_node_id"]
    session.add(Note(user_id=1, node_id=node_id, body="Personal notes added after adoption"))
    session.add(Progress(user_id=1, node_id=node_id, status="done"))
    changed = [{**mapping, "outcome": "none_fits", "primary_node_id": None,
        "secondary_node_ids": [], "evidence": {}} for mapping in imported.mappings]
    corrected = review_classification(session, imported.id, 9, changed, imported.id,
        baseline_revision, "baseline-subsequent-correction", note="Compared complete source")
    session.commit()
    rollback_baseline(session, frozen["release_id"], frozen["manifest_hash"], 9)
    session.commit()
    assert session.get(Note, (1, node_id)).body == "Personal notes added after adoption"
    assert session.get(Progress, (1, node_id)).status == "done"
    assert session.get(ClassificationRevision, corrected["revision_id"]) is not None
    assert session.get(QuestionPublication, imported.question_id).current_revision_id == corrected["revision_id"]
    assert session.get(BaselineAdoption, frozen["release_id"]).status == "inactive"
