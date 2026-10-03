"""Versioned textbook explorer and authenticated release review."""
from datetime import datetime, timezone
from typing import Any
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from caf_api.auth import Principal, require_account, require_admin
from caf_api.routes import get_db, get_operations_db
from caf_api.curate import get_curation_db
from caf_contracts.taxonomy import (DescriptorEdit, DescriptorReview, SourceReview,
    CrosswalkReview, ReleaseApproval, ReleaseActivation, ReleaseSummary, TaxonomyTreeNode)
from caf_db.models.taxonomy import (TaxonomyRelease, TaxonomyCrosswalk,
    TextbookArtifact, NodeSourceSpan, DescriptorRevision, DescriptorApproval)
from caf_db.models.app import Progress, Note
from caf_db.models.ref import Node
from caf_l0.releases import (get_release, version_nodes, source_context, source_contexts,
    latest_descriptor, descriptor_approved, eligible_candidates, release_report,
    revise_descriptor, approve_descriptor, approve_release, activate_release)

router = APIRouter(prefix="/api/v1/taxonomy", tags=["textbook taxonomy"], dependencies=[Depends(require_account)])


def checked(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/versions", response_model=list[ReleaseSummary])
def versions(db: Session = Depends(get_db)):
    return [{"version_id": r.version_id, "taxonomy_version_id": r.taxonomy_version_id,
             "target_attempt": r.target_attempt, "status": r.status,
             "manifest_hash": r.manifest_hash, "approved_by": r.approved_by,
             "activated_at": r.activated_at.isoformat() if r.activated_at else None}
            for r in db.scalars(sa.select(TaxonomyRelease).order_by(TaxonomyRelease.taxonomy_version_id.desc()))]


@router.get("/versions/{version_id}/tree", response_model=list[TaxonomyTreeNode])
def tree(version_id: str, paper_id: str | None = None, db: Session = Depends(get_db)):
    release = checked(get_release, db, version_id)
    members = version_nodes(db, release.taxonomy_version_id, paper_id)
    eligible = {n.node_id for n in eligible_candidates(db, release.taxonomy_version_id, paper_id)}
    by_id = {m.node_id: m for m in members}
    all_sources = source_contexts(db, release.taxonomy_version_id)
    descriptors = {r.node_id: r for r in db.scalars(sa.select(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id).order_by(DescriptorRevision.revision))}
    approvals = {a.revision_id: a.content_hash for a in db.scalars(sa.select(DescriptorApproval).join(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id))}
    values = {}
    for member in members:
        breadcrumbs = []
        ancestor = member
        while ancestor:
            breadcrumbs.insert(0, {"id": ancestor.node_id, "name": ancestor.name, "level": ancestor.level})
            ancestor = by_id.get(ancestor.parent_id)
        sources = all_sources.get(member.node_id, [])
        descriptor = descriptors.get(member.node_id)
        values[member.node_id] = dict(id=member.node_id, paper_id=member.paper_id,
            parent_id=member.parent_id, level=member.level, name=member.name, seq=member.seq,
            heading_origin=member.heading_origin,
            source_review_status="reviewed" if sources and all(s["review_status"] == "reviewed" for s in sources) else "pending",
            descriptor_revision=descriptor.revision if descriptor else None,
            descriptor_approved=descriptor is not None and approvals.get(descriptor.id) == descriptor.content_hash,
            eligible=member.node_id in eligible, breadcrumbs=breadcrumbs, sources=sources, children=[])
    roots = []
    for member in members:
        if member.parent_id in values:
            values[member.parent_id]["children"].append(values[member.node_id])
        else:
            roots.append(values[member.node_id])
    return roots


@router.get("/versions/{version_id}/sources", response_model=list[dict[str, Any]])
def sources(version_id: str, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    release = checked(get_release, db, version_id)
    return [s.metadata_json for s in db.scalars(sa.select(TextbookArtifact).where(TextbookArtifact.taxonomy_version_id == release.taxonomy_version_id).order_by(TextbookArtifact.paper_id, TextbookArtifact.id))]


@router.get("/versions/{version_id}/question-sources", response_model=list[dict[str, Any]])
def question_sources(version_id: str, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    release = checked(get_release, db, version_id)
    return release.manifest.get("question_sources", [])


@router.get("/versions/{version_id}/crosswalk", response_model=list[dict[str, Any]])
def crosswalk(version_id: str, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    release = checked(get_release, db, version_id)
    return [{"id": m.id, "old_node_id": m.old_node_id, "new_node_id": m.new_node_id,
             "relation": m.relation, "evidence": m.evidence, "reviewed_by": m.reviewed_by,
             "reviewed_at": m.reviewed_at.isoformat() if m.reviewed_at else None}
            for m in db.scalars(sa.select(TaxonomyCrosswalk).where(TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id))]


@router.post("/crosswalk/{mapping_id}/approve", response_model=dict[str, Any])
def review_crosswalk(mapping_id: int, body: CrosswalkReview, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    release = checked(get_release, db, body.version_id)
    mapping = db.get(TaxonomyCrosswalk, mapping_id)
    if mapping is None or mapping.taxonomy_version_id != release.taxonomy_version_id:
        raise HTTPException(404, "Mapping not in release")
    mapping.reviewed_by, mapping.reviewed_at = admin.id, datetime.now(timezone.utc)
    db.commit()
    return {"id": mapping.id, "reviewed_by": mapping.reviewed_by}


@router.get("/versions/{version_id}/report", response_model=dict[str, Any])
def report(version_id: str, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    # Operational role has no access to personal tables. Counts are read through
    # the student role and only expose aggregate preservation evidence.
    return checked(release_report, db, version_id, include_personal_counts=False)


@router.post("/versions/{version_id}/approve", response_model=dict[str, Any])
def approve(version_id: str, body: ReleaseApproval, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    result = checked(approve_release, db, version_id, body.manifest_hash, admin.id)
    db.commit()
    return result


@router.post("/versions/{version_id}/activate", response_model=dict[str, Any])
def activate(version_id: str, body: ReleaseActivation, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    result = checked(activate_release, db, version_id, body.manifest_hash, dry_run=body.dry_run)
    db.commit()
    return result


@router.get("/nodes/{node_id}/descriptor", response_model=dict[str, Any] | None)
def descriptor(node_id: str, version_id: str, db: Session = Depends(get_db)):
    release = checked(get_release, db, version_id)
    revision = latest_descriptor(db, release.taxonomy_version_id, node_id)
    return {**revision.content, "revision": revision.revision, "approved": descriptor_approved(db, revision)} if revision else None


@router.put("/nodes/{node_id}/descriptor", response_model=dict[str, Any])
def edit_descriptor(node_id: str, body: DescriptorEdit, db: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    revision = checked(revise_descriptor, db, body.version_id, node_id, body.model_dump(exclude={"version_id"}), account.id)
    db.commit()
    return {"revision": revision.revision, "approved": False}


@router.post("/nodes/{node_id}/descriptor/approve", response_model=dict[str, Any])
def review_descriptor(node_id: str, body: DescriptorReview, db: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    revision = checked(approve_descriptor, db, body.version_id, node_id, body.revision, account.id)
    db.commit()
    return {"revision": revision.revision, "approved": True}


@router.post("/nodes/{node_id}/source/approve", response_model=dict[str, Any])
def review_source(node_id: str, body: SourceReview, db: Session = Depends(get_operations_db), admin: Principal = Depends(require_admin)):
    release = checked(get_release, db, body.version_id)
    spans = list(db.scalars(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == release.taxonomy_version_id, NodeSourceSpan.node_id == node_id)))
    if not spans:
        raise HTTPException(404, "Source spans not found")
    for span in spans:
        artifact = db.get(TextbookArtifact, (span.taxonomy_version_id, span.artifact_id))
        if artifact.availability != "verified":
            raise HTTPException(422, "Artifact must be verified before source review")
        span.review_status, span.reviewed_by = "reviewed", admin.id
    db.commit()
    return {"node_id": node_id, "review_status": "reviewed"}


@router.get("/nodes/{node_id}/history", response_model=dict[str, Any])
def history(node_id: str, version_id: str, db: Session = Depends(get_db), account: Principal = Depends(require_account)):
    release = checked(get_release, db, version_id)
    mappings = list(db.scalars(sa.select(TaxonomyCrosswalk).where(TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id, TaxonomyCrosswalk.new_node_id == node_id)))
    node_ids = [(node_id, "current")] + [(m.old_node_id, m.relation) for m in mappings]
    records = []
    for record_id, relation in node_ids:
        node = db.get(Node, record_id)
        if not node: continue
        progress = db.get(Progress, (account.id, record_id))
        note = db.get(Note, (account.id, record_id))
        records.append({"node_id": record_id, "name": node.name, "relation": relation,
            "progress": {"status": progress.status, "first_done_at": progress.first_done_at, "last_revised_at": progress.last_revised_at} if progress else None,
            "note": {"body": note.body, "updated_at": note.updated_at} if note else None})
    return {"node_id": node_id, "records": records}
