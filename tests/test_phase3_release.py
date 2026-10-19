"""Deterministic textbook release gates exercised on isolated PostgreSQL."""
from copy import deepcopy
import hashlib
import json
from uuid import uuid4
import fitz
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from caf_db.engine import get_engine
from caf_db.models.app import UserAccount, Progress, Note
from caf_db.models.ref import Node
from caf_db.models.taxonomy import (TaxonomyRelease, TaxonomyMember, DescriptorRevision,
    NodeSourceSpan, TaxonomyCrosswalk, ProgressMigration, TextbookArtifact)
from caf_l0.releases import (import_release, validate_manifest, approve_descriptor,
    revise_descriptor, eligible_candidates, release_report, approve_release,
    activate_release, active_version, migrate_exact_progress)


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "textbook.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Official textbook fixture")
        pdf.save(path)
    manifest = dict(version_id="textbook-fixture", target_attempt="2027-05",
        papers=[f"s2023.P{i}" for i in range(1, 7)], textbook_artifacts=[], nodes=[], descriptors=[], crosswalk=[],
        heading_reconciliation={"status": "complete", "expected_count": 30, "accounted_count": 30, "unresolved": []})
    for i in range(1, 7):
        paper = f"s2023.P{i}"
        artifact_id = f"fixture-{i}"
        manifest["textbook_artifacts"].append(dict(id=artifact_id, paper_id=paper,
            course_level="Final", edition="January 2026", applicable_attempts=["2026-01"],
            landing_url="https://www.icai.org/fixture", download_url="https://resource.cdn.icai.org/fixture.pdf",
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), local_path=str(path),
            retrieved_at="2026-10-03", page_count=1, edition_evidence="January 2026 applicability fixture",
            availability="verified", fallback=True, target_applicability="unresolved", expected_structure=["Module 1"]))
        parent = None
        span = dict(artifact_id=artifact_id, pdf_page_start=1, pdf_page_end=1)
        for ordinal, kind in enumerate(("module", "chapter", "unit", "topic", "subtopic")):
            node_id = str(uuid4())
            manifest["nodes"].append(dict(id=node_id, paper_id=paper, parent_id=parent, kind=kind,
                name=f"{kind} {i}", ordinal=ordinal, heading_origin="official", source_spans=[span]))
            parent = node_id
        manifest["descriptors"].append(dict(node_id=parent, revision=1, definition="Time value of money",
            terminology=["discounting"], inclusion=["present value"], exclusion=["audit risk"],
            nearby_distinctions=["Future value accumulates cash flows"], source_spans=[span]))
    return manifest


def authenticated_actors(session):
    student = session.get(UserAccount, 1)
    student.status = "active"
    student.role = "student"
    session.add(UserAccount(id=9, name="Release administrator", role="administrator", status="active"))
    session.commit()


def review_all(session, version_id):
    release = session.get(TaxonomyRelease, version_id)
    for span in session.scalars(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == release.taxonomy_version_id)):
        span.review_status, span.reviewed_by = "reviewed", 9
    for revision in session.scalars(sa.select(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id)):
        approve_descriptor(session, version_id, revision.node_id, revision.revision, 1)
    session.flush()


def test_dry_run_fresh_ids_recursive_and_immutable(session, manifest):
    manifest["descriptors"][0].update(edition="November 2024", instrument_references=["Ind AS 109"])
    legacy_ids = set(session.scalars(sa.select(Node.id)))
    legacy_id = sorted(legacy_ids)[0]
    evidence = {"legacy_name": "Original source concept", "review_note": "No reviewed equivalence"}
    manifest["crosswalk"] = [dict(old_node_id=legacy_id, new_node_id=None,
                                  relation="unresolved", evidence=evidence)]
    report = import_release(session, manifest)
    assert report["dry_run"] and report["node_count"] == 30
    assert session.get(TaxonomyRelease, manifest["version_id"]) is None
    import_release(session, manifest, dry_run=False)
    session.commit()
    release = session.get(TaxonomyRelease, manifest["version_id"])
    mapping = session.scalar(sa.select(TaxonomyCrosswalk).where(
        TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id))
    assert json.loads(mapping.evidence) == evidence
    content = session.scalar(sa.select(DescriptorRevision).where(DescriptorRevision.node_id == manifest["descriptors"][0]["node_id"])).content
    assert content["edition"] == "November 2024" and content["instrument_references"] == ["Ind AS 109"]
    assert set(n["id"] for n in manifest["nodes"]).isdisjoint(legacy_ids)
    assert len(eligible_candidates(session, release.taxonomy_version_id)) == 0
    assert import_release(session, manifest, dry_run=False)["node_count"] == 30
    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(sa.update(TaxonomyMember).where(TaxonomyMember.taxonomy_version_id == release.taxonomy_version_id).values(name="tampered"))
    session.rollback()
    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(sa.update(Node).where(Node.id == manifest["nodes"][4]["id"]).values(parent_id=manifest["nodes"][0]["id"]))
    session.rollback()


def test_source_ambiguities_survive_import_and_require_resolution(session, manifest):
    authenticated_actors(session)
    manifest["descriptors"][0]["source_ambiguities"] = ["Truncated textbook heading"]
    import_release(session, manifest, dry_run=False)
    node_id = manifest["descriptors"][0]["node_id"]
    revision = session.scalar(sa.select(DescriptorRevision).where(DescriptorRevision.node_id == node_id))
    with pytest.raises(ValueError, match="source issues"):
        approve_descriptor(session, manifest["version_id"], node_id, 1, 1)
    revised = revise_descriptor(session, manifest["version_id"], node_id,
        {**revision.content, "definition": "Verified complete concept definition", "source_ambiguities": []}, 1)
    approve_descriptor(session, manifest["version_id"], node_id, revised.revision, 1)


def test_reject_cycle_duplicate_and_forged_verified_bytes(manifest):
    bad = deepcopy(manifest)
    bad["nodes"][0]["parent_id"] = bad["nodes"][4]["id"]
    with pytest.raises(ValueError, match="cycle"):
        validate_manifest(bad)
    bad = deepcopy(manifest)
    bad["nodes"].append(bad["nodes"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_manifest(bad)
    bad = deepcopy(manifest)
    bad["textbook_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="bytes"):
        validate_manifest(bad)


def test_descriptor_eligibility_edit_and_approved_activation(session, manifest):
    authenticated_actors(session)
    report = import_release(session, manifest, dry_run=False)
    release = session.get(TaxonomyRelease, manifest["version_id"])
    with pytest.raises(ValueError, match="unresolved"):
        approve_release(session, release.version_id, report["manifest_hash"], 9)
    review_all(session, release.version_id)
    assert len(eligible_candidates(session, release.taxonomy_version_id)) == 6
    with pytest.raises(ValueError, match="administrator"):
        approve_release(session, release.version_id, report["manifest_hash"], 1)
    approve_release(session, release.version_id, report["manifest_hash"], 9)
    activate_release(session, release.version_id, report["manifest_hash"])
    assert active_version(session) is None
    activate_release(session, release.version_id, report["manifest_hash"], dry_run=False)
    activate_release(session, release.version_id, report["manifest_hash"], dry_run=False)
    assert active_version(session).version_id == release.version_id
    node_id = manifest["descriptors"][0]["node_id"]
    revision = session.scalar(sa.select(DescriptorRevision).where(DescriptorRevision.node_id == node_id))
    revise_descriptor(session, release.version_id, node_id, {**revision.content, "definition": "Edited present value boundary"}, 1)
    assert len(eligible_candidates(session, release.taxonomy_version_id)) == 5
    assert session.get(TaxonomyRelease, release.version_id).approved_by is None
    with pytest.raises(ValueError, match="changed"):
        approve_descriptor(session, release.version_id, node_id, 1, 1)


def test_progress_exact_only_preserves_original_notes(session, manifest):
    authenticated_actors(session)
    old = session.scalar(sa.select(Node).where(Node.level == "subtopic").order_by(Node.id))
    session.add(Progress(user_id=1, node_id=old.id, status="done"))
    session.add(Note(user_id=1, node_id=old.id, body="Original private note"))
    import_release(session, manifest, dry_run=False)
    release = session.get(TaxonomyRelease, manifest["version_id"])
    new_id = manifest["descriptors"][0]["node_id"]
    mapping = TaxonomyCrosswalk(taxonomy_version_id=release.taxonomy_version_id, old_node_id=old.id, new_node_id=new_id, relation="exact", evidence="Textbook boundaries reviewed", reviewed_by=9)
    session.add(mapping)
    session.flush()
    assert migrate_exact_progress(session, release.version_id)["transferred"] == 1
    assert session.get(Progress, (1, new_id)) is None
    migrate_exact_progress(session, release.version_id, dry_run=False)
    assert session.get(Progress, (1, old.id)).status == "done"
    assert session.get(Progress, (1, new_id)).status == "done"
    assert session.get(Note, (1, old.id)).body == "Original private note"
    assert session.get(Note, (1, new_id)) is None
    assert session.get(ProgressMigration, (1, mapping.id)) is not None
    assert migrate_exact_progress(session, release.version_id, dry_run=False)["transferred"] == 0


def test_actual_curation_role_can_review_but_cannot_activate(session, manifest):
    from sqlalchemy.orm import Session
    authenticated_actors(session)
    import_release(session, manifest, dry_run=False)
    session.commit()
    node_id = manifest["descriptors"][0]["node_id"]
    with Session(get_engine("curation")) as curator:
        approve_descriptor(curator, manifest["version_id"], node_id, 1, 1)
        curator.commit()
        with pytest.raises(DBAPIError, match="permission denied"):
            curator.execute(sa.update(TaxonomyRelease).values(status="active"))
        curator.rollback()


def test_recursive_explorer_admin_reviews_and_private_predecessor_notes(session, manifest, authenticated_client):
    import_release(session, manifest, dry_run=False)
    old = session.scalar(sa.select(Node).where(Node.level == "subtopic").order_by(Node.id))
    release = session.get(TaxonomyRelease, manifest["version_id"])
    new_id = manifest["descriptors"][0]["node_id"]
    session.add(TaxonomyCrosswalk(taxonomy_version_id=release.taxonomy_version_id, old_node_id=old.id,
        new_node_id=new_id, relation="unresolved", evidence="Pending boundary comparison"))
    session.add(Note(user_id=1, node_id=old.id, body="Private predecessor note"))
    session.commit()
    owner = authenticated_client(1)
    stranger = authenticated_client(2)
    admin = authenticated_client(9, role="administrator")
    url = f"/api/v1/taxonomy/versions/{release.version_id}"
    response = owner.get(url + "/tree", params={"paper_id": "s2023.P1"})
    assert response.status_code == 200, response.text
    leaf = response.json()[0]
    while leaf["children"]:
        leaf = leaf["children"][0]
    assert len(leaf["breadcrumbs"]) == 5 and leaf["sources"][0]["fallback"] is True
    for suffix in ("sources", "crosswalk", "report"):
        assert owner.get(url + "/" + suffix).status_code == 403
        assert admin.get(url + "/" + suffix).status_code == 200
    history_url = f"/api/v1/taxonomy/nodes/{new_id}/history?version_id={release.version_id}"
    assert any(r["note"] and r["note"]["body"] == "Private predecessor note" for r in owner.get(history_url).json()["records"])
    assert all(r["note"] is None for r in stranger.get(history_url).json()["records"])
    review_url = f"/api/v1/taxonomy/nodes/{new_id}/descriptor/approve"
    assert owner.post(review_url, json={"version_id": release.version_id, "revision": 1}).status_code == 200
    content = {k: v for k, v in owner.get(f"/api/v1/taxonomy/nodes/{new_id}/descriptor?version_id={release.version_id}").json().items() if k not in {"revision", "approved"}}
    edited = owner.put(f"/api/v1/taxonomy/nodes/{new_id}/descriptor", json={**content, "version_id": release.version_id, "definition": "Edited concept"})
    assert edited.status_code == 200 and edited.json()["approved"] is False, edited.text


def test_partial_release_keeps_unverified_expected_source_gap_explicit(session, manifest):
    manifest["textbook_artifacts"][0].update(availability="inaccessible", sha256=None,
        local_path=None, expected_structure=["Module 1", "Missing Module 2"])
    manifest["source_gaps"] = [dict(paper_id="s2023.P1", status="unresolved",
        reason="Module 2 January 2026 download unavailable")]
    import_release(session, manifest, dry_run=False)
    report = release_report(session, manifest["version_id"])
    assert report["unresolved_sources"] == ["fixture-1"]
    assert "Expected textbook structure has unresolved gaps" in report["blockers"]
    assert "s2023.P1: Module 2 January 2026 download unavailable" in report["blockers"]
    assert not report["activation_ready"]


def test_revised_release_reuses_exact_textbook_identities_and_preserves_prior_review(session, manifest):
    from caf_l0.releases import source_context
    authenticated_actors(session)
    manifest["source_gaps"] = [dict(paper_id="s2023.P1", status="unresolved",
        reason="One expected concept awaiting heading reconciliation")]
    manifest["heading_reconciliation"] = {"status": "pending", "expected_count": 31,
        "accounted_count": 30, "unresolved": ["Missing concept"]}
    import_release(session, manifest, dry_run=False)
    original = session.get(TaxonomyRelease, manifest["version_id"])
    review_all(session, original.version_id)
    first_leaf = manifest["descriptors"][0]["node_id"]
    session.add(Progress(user_id=1, node_id=first_leaf, status="done"))
    session.add(Note(user_id=1, node_id=first_leaf, body="Keep my original textbook note"))
    session.commit()
    original_hash = original.manifest_hash
    revised = deepcopy(manifest)
    revised["version_id"] = "textbook-fixture-resolved"
    revised["source_gaps"] = []
    revised["heading_reconciliation"] = {"status": "complete", "expected_count": 31,
        "accounted_count": 31, "unresolved": []}
    new_node = deepcopy(revised["nodes"][4])
    new_node.update(id=str(uuid4()), name="Newly reconciled concept", ordinal=5)
    revised["nodes"].append(new_node)
    new_descriptor = deepcopy(revised["descriptors"][0])
    new_descriptor["node_id"] = new_node["id"]
    revised["descriptors"].append(new_descriptor)
    revised["textbook_artifacts"][0]["target_applicability"] = "review_required"
    preview = import_release(session, revised)
    assert preview["node_count"] == 31
    assert session.get(TaxonomyRelease, revised["version_id"]) is None
    import_release(session, revised, dry_run=False)
    session.commit()
    successor = session.get(TaxonomyRelease, revised["version_id"])
    assert successor.taxonomy_version_id != original.taxonomy_version_id
    assert session.get(TaxonomyRelease, original.version_id).manifest_hash == original_hash
    assert session.get(TaxonomyRelease, original.version_id).manifest["source_gaps"]
    assert len(eligible_candidates(session, original.taxonomy_version_id)) == 6
    assert eligible_candidates(session, successor.taxonomy_version_id) == []
    assert session.scalar(sa.select(sa.func.count()).select_from(TaxonomyMember).where(
        TaxonomyMember.taxonomy_version_id == original.taxonomy_version_id)) == 30
    assert session.scalar(sa.select(sa.func.count()).select_from(TaxonomyMember).where(
        TaxonomyMember.taxonomy_version_id == successor.taxonomy_version_id)) == 31
    assert session.get(Node, first_leaf).created_in == original.taxonomy_version_id
    assert session.get(Progress, (1, first_leaf)).status == "done"
    assert session.get(Note, (1, first_leaf)).body == "Keep my original textbook note"
    assert session.get(TextbookArtifact, (original.taxonomy_version_id, "fixture-1")).metadata_json["target_applicability"] == "unresolved"
    assert source_context(session, successor.taxonomy_version_id, first_leaf)[0]["target_applicability"] == "review_required"
    incompatible = deepcopy(revised)
    incompatible["version_id"] = "textbook-fixture-conflicting"
    incompatible["nodes"][4]["name"] = "Different conceptual identity"
    with pytest.raises(ValueError, match="incompatible immutable"):
        import_release(session, incompatible)
    legacy_node = session.scalar(sa.select(Node).where(Node.id.not_in([n["id"] for n in revised["nodes"]])).limit(1))
    incompatible["nodes"][4]["id"] = legacy_node.id
    incompatible["descriptors"][0]["node_id"] = legacy_node.id
    with pytest.raises(ValueError, match="legacy"):
        import_release(session, incompatible)


def test_review_report_rejects_manifest_drift_and_missing_representative_sources(session, manifest):
    authenticated_actors(session)
    manifest["question_inventory_gaps"] = [{"course_level": "Final", "source_family": "mock", "availability": "inaccessible"}]
    import_release(session, manifest, dry_run=False)
    release = session.get(TaxonomyRelease, manifest["version_id"])
    node_id = str(uuid4())
    session.add(Node(id=node_id, paper_id="s2023.P1", parent_id=None, level="module", name="Unsupported extra module", seq=99))
    session.flush()
    session.add(TaxonomyMember(taxonomy_version_id=release.taxonomy_version_id, node_id=node_id,
        paper_id="s2023.P1", parent_id=None, level="module", name="Unsupported extra module", seq=99, heading_origin="official"))
    session.flush()
    review_all(session, release.version_id)
    report = release_report(session, release.version_id)
    assert "Persisted hierarchy differs from the immutable manifest" in report["blockers"]
    assert "Source context awaiting review" in report["blockers"]
    assert "Representative Final question sources awaiting verification" in report["blockers"]
    assert not report["activation_ready"]
