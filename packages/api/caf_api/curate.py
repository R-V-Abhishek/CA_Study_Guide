"""Curator API endpoints for document review and catalog confirmation."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_api.routes import get_operations_db
from caf_api.auth import Principal, require_account, require_admin
from caf_db.engine import get_session_factory
from caf_l1.catalog import confirm_document, reject_document
from caf_db.models.ingest import Document
from caf_contracts.extraction import PaperPageRange
from caf_contracts.classification import (
    ClassificationQueueItem, ClassificationReviewRequest, ClassificationVerificationRequest,
    ClassificationDisputeRequest, ClassificationResolveRequest, ClassificationRevisionResult,
    ClassificationHistoryItem, ClassificationDisputeResult, ClassificationBulkRequest,
    ClassificationBulkResult,
)
from caf_api.responses import (
    BulkAcceptResult, CuratorDecisionResult, CuratorDocument, CuratorQueueItem,
    DocumentConfirmResult, DocumentEditResult, DocumentStatusResult, RecomputeResult,
)

router = APIRouter(prefix="/api/v1/curate", tags=["curation"], dependencies=[Depends(require_account)])


def get_curation_db():
    with get_session_factory("curation")() as session:
        yield session


class DocumentEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str | None = None
    paper_id: str | None = None
    doc_type_id: str | None = None
    series: str | None = None
    part: str | None = None
    title: str | None = None


class DocumentConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_level: Literal["foundation", "intermediate", "final"] | None = None
    scheme_id: str | None = None
    collection_id: str | None = None
    paper_page_ranges: list[PaperPageRange] | None = None
    attempt_id: str | None = None
    paper_id: str | None = None
    doc_type_id: str | None = None
    series: str | None = None
    part: str | None = None
    title: str | None = None


@router.get("/documents", response_model=list[CuratorDocument])
def list_curate_documents(
    status: str | None = Query(None, description="inferred, needs_curation, confirmed, rejected"),
    attempt_id: str | None = None,
    paper_id: str | None = None,
    session: Session = Depends(get_operations_db),
    account: Principal = Depends(require_admin),
):
    query = sa.select(Document).where(Document.superseded.is_(False)).order_by(Document.id.desc())
    if status:
        query = query.where(Document.catalog_status == status)
    if attempt_id:
        query = query.where(Document.attempt_id == attempt_id)
    if paper_id:
        query = query.where(Document.paper_id == paper_id)

    docs = session.execute(query).scalars().all()
    return [
        {
            "id": d.id,
            "sha256": d.sha256,
            "course_level": d.course_level,
            "provenance_status": d.provenance_status,
            "title": d.title,
            "scheme_id": d.scheme_id,
            "attempt_id": d.attempt_id,
            "paper_id": d.paper_id,
            "doc_type_id": d.doc_type_id,
            "series": d.series,
            "part": d.part,
            "catalog_status": d.catalog_status,
            "extract_status": d.extract_status,
            "page_count": d.page_count,
            "bytes": d.bytes,
            "origin": d.origin,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@router.post("/documents/{doc_id}/confirm", response_model=DocumentConfirmResult)
def api_confirm_document(
    doc_id: int,
    req: DocumentConfirmRequest | None = None,
    session: Session = Depends(get_operations_db),
    account: Principal = Depends(require_admin),
):
    overrides = req.model_dump(exclude_unset=True) if req else None
    try:
        doc = confirm_document(session, doc_id, overrides=overrides,actor_id=account.id)
        return {
            "id": doc.id,
            "catalog_status": doc.catalog_status,
            "attempt_id": doc.attempt_id,
            "paper_id": doc.paper_id,
            "doc_type_id": doc.doc_type_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/{doc_id}/reject", response_model=DocumentStatusResult)
def api_reject_document(doc_id: int, session: Session = Depends(get_operations_db), account: Principal = Depends(require_admin)):
    try:
        doc = reject_document(session, doc_id)
        return {"id": doc.id, "catalog_status": doc.catalog_status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/documents/{doc_id}", response_model=DocumentEditResult)
def api_edit_document(
    doc_id: int,
    req: DocumentEditRequest,
    session: Session = Depends(get_operations_db),
    account: Principal = Depends(require_admin),
):
    from caf_l1.catalog import lock_document_metadata
    lock_document_metadata(session, doc_id)
    doc = session.get(Document, doc_id, populate_existing=True)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(doc, k, v)

    session.commit()
    return {"id": doc.id, "title": doc.title, "catalog_status": doc.catalog_status}


# ==============================================================================
# Tag Review Queue & Curation Decisions
# ==============================================================================


@router.get('/classifications', response_model=list[ClassificationQueueItem])
def classification_queue(
    paper_id: str | None = None, source: str | None = None, outcome: str | None = None,
    question_id: str | None = Query(None, min_length=1, description="Exact affected question identity"),
    taxonomy_version_id: int | None = None, experimental: bool | None = None,
    ready: bool | None = None, disputed: bool | None = None, blind: bool = False,
    benchmark_only: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_account),
):
    """One immutable suggestion per root, retaining the previous publication during review."""
    from caf_db.models.classification import (SuggestionRevision, ClassificationRevision,
        QuestionPublication, ClassificationVerification, ClassificationDispute)
    from caf_l4.revisions import readiness, taxonomy_readiness_evidence

    latest_query = sa.select(sa.func.max(SuggestionRevision.id).label('id'))
    if taxonomy_version_id:
        latest_query = latest_query.where(SuggestionRevision.taxonomy_version_id == taxonomy_version_id)
    if question_id:
        latest_query = latest_query.where(SuggestionRevision.question_id == question_id)
    latest = latest_query.group_by(SuggestionRevision.question_id).subquery()
    query = sa.select(SuggestionRevision, Document).join(latest, SuggestionRevision.id == latest.c.id).join(Document, Document.id == SuggestionRevision.document_id)
    if paper_id: query = query.where(SuggestionRevision.context['paper_id'].astext == paper_id)
    if source: query = query.where(Document.doc_type_id == source)
    if taxonomy_version_id: query = query.where(SuggestionRevision.taxonomy_version_id == taxonomy_version_id)
    if experimental is not None: query = query.where(SuggestionRevision.experimental == experimental)
    result = []
    skipped = 0
    # Evidence is shared only within this read request. Mutations always load
    # current evidence again, so approvals/corrections cannot use stale gates.
    taxonomy_evidence = {}
    for suggestion, document in session.execute(query.order_by(SuggestionRevision.id.desc())):
        version_id = suggestion.taxonomy_version_id
        if version_id not in taxonomy_evidence:
            taxonomy_evidence[version_id] = taxonomy_readiness_evidence(session, version_id)
        gate = readiness(session, suggestion, taxonomy_evidence[version_id])
        if ready is not None and gate['eligible'] != ready: continue
        if outcome and not any(part['outcome'] == outcome for part in suggestion.mappings): continue
        benchmark = bool(suggestion.provenance.get('benchmark', False))
        if benchmark_only and not benchmark: continue
        publication = session.get(QuestionPublication, suggestion.question_id)
        current_id = publication.current_revision_id if publication else None
        current = session.get(ClassificationRevision, current_id) if current_id else None
        count = session.scalar(sa.select(sa.func.count()).select_from(ClassificationVerification).where(
            ClassificationVerification.revision_id == current_id, ClassificationVerification.active.is_(True))) if current_id else 0
        mine = session.scalar(sa.select(ClassificationVerification.id).where(ClassificationVerification.revision_id == current_id,
            ClassificationVerification.actor_id == account.id, ClassificationVerification.active.is_(True))) if current_id else None
        dispute = session.scalar(sa.select(ClassificationDispute).where(ClassificationDispute.question_id == suggestion.question_id,
            ClassificationDispute.status == 'open').order_by(ClassificationDispute.id.desc()).limit(1))
        if disputed is not None and bool(dispute) != disputed: continue
        if skipped < offset:
            skipped += 1
            continue
        mappings = suggestion.mappings if not blind else [dict(part_id=part['part_id'], outcome='needs_review') for part in suggestion.mappings]
        question = {key: value for key, value in suggestion.context.items() if key != 'classification_part_ids'}
        result.append(dict(suggestion_revision_id=suggestion.id, document_id=document.id, question_id=suggestion.question_id,
            extraction_revision_id=suggestion.extraction_revision_id, taxonomy_version_id=suggestion.taxonomy_version_id,
            run_id=None if blind else suggestion.run_id, input_hash=suggestion.input_hash, paper_id=suggestion.context['paper_id'],
            attempt_id=document.attempt_id, doc_type_id=document.doc_type_id, experimental=suggestion.experimental,
            stale=gate['stale'], publication_ready=gate['eligible'],
            readiness_blockers=[dict(code=str(block), message=str(block)) for block in gate['blockers']],
            question=question, mappings=mappings, candidates=suggestion.candidates,
            provenance={} if blind else suggestion.provenance, publication_revision_id=current_id,
            publication_suggestion_revision_id=current.suggestion_revision_id if current else None,
            published_question={key: value for key, value in current.context.items() if key != 'classification_part_ids'} if current and not blind else None,
            published_mappings=[] if blind or not current else current.mappings,
            verification_count=count, verified_by_me=bool(mine), dispute_status=dispute.status if dispute else None,
            is_benchmark=benchmark, blind=blind))
        if len(result) >= limit: break
    return result


def classification_mutation(session, operation):
    from caf_l4.revisions import RevisionConflict, ReadinessError
    try:
        result = operation()
        session.commit()
        return result
    except RevisionConflict as exc:
        session.rollback()
        raise HTTPException(409, dict(code='stale_revision', message=str(exc), current_revision_id=exc.current_revision_id)) from exc
    except ReadinessError as exc:
        session.rollback()
        raise HTTPException(422, dict(code='readiness_failed', message=str(exc), blockers=exc.blockers)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(422, dict(code='invalid_classification', message=str(exc))) from exc


@router.post('/classifications/{suggestion_id}/review', response_model=ClassificationRevisionResult)
def classification_review(suggestion_id: int, body: ClassificationReviewRequest,
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    from caf_l4.revisions import review_classification
    return classification_mutation(session, lambda: review_classification(session, suggestion_id, account.id,
        **body.model_dump()))


@router.post('/classifications/bulk', response_model=ClassificationBulkResult)
def classification_bulk(body: ClassificationBulkRequest, session: Session = Depends(get_curation_db),
    account: Principal = Depends(require_admin)):
    from caf_l4.revisions import review_classification
    return classification_mutation(session, lambda: dict(revisions=[review_classification(session,
        review.expected_suggestion_revision_id, account.id, **review.model_dump()) for review in body.reviews]))


@router.get('/classifications/questions/{question_id}/history', response_model=list[ClassificationHistoryItem])
def classification_history(question_id: str, session: Session = Depends(get_curation_db)):
    from caf_l4.revisions import history
    return history(session, question_id)


@router.post('/classifications/questions/{question_id}/verify', response_model=ClassificationRevisionResult)
def classification_verify(question_id: str, body: ClassificationVerificationRequest,
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    from caf_l4.revisions import verify_classification
    return classification_mutation(session, lambda: verify_classification(session, question_id, account.id, **body.model_dump()))


@router.post('/classifications/questions/{question_id}/withdraw', response_model=ClassificationRevisionResult)
def classification_withdraw(question_id: str, body: ClassificationVerificationRequest,
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    from caf_l4.revisions import verify_classification
    return classification_mutation(session, lambda: verify_classification(session, question_id, account.id, withdraw=True, **body.model_dump()))


@router.post('/classifications/questions/{question_id}/disputes', response_model=ClassificationRevisionResult)
def classification_dispute(question_id: str, body: ClassificationDisputeRequest,
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_account)):
    from caf_l4.revisions import submit_dispute
    return classification_mutation(session, lambda: submit_dispute(session, question_id, account.id, **body.model_dump()))


@router.get('/classifications/questions/{question_id}/disputes', response_model=list[ClassificationDisputeResult])
def classification_disputes(question_id: str, session: Session = Depends(get_curation_db)):
    from caf_db.models.classification import ClassificationDispute
    return [dict(id=row.id, classification_revision_id=row.revision_id, status=row.status, reason=row.reason)
        for row in session.scalars(sa.select(ClassificationDispute).where(ClassificationDispute.question_id == question_id).order_by(ClassificationDispute.id.desc()))]


@router.post('/classifications/disputes/{dispute_id}/resolve', response_model=ClassificationRevisionResult)
def classification_resolve(dispute_id: int, body: ClassificationResolveRequest,
    session: Session = Depends(get_curation_db), account: Principal = Depends(require_admin)):
    from caf_l4.revisions import resolve_dispute
    return classification_mutation(session, lambda: resolve_dispute(session, dispute_id, account.id, **body.model_dump()))

class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "accept_alt", "edit", "none_fits", "exclude", "bulk_accept", "undo"]
    primary_node_id: str | None = None
    secondary_node_ids: list[str] = []
    gist: str | None = None
    seconds_spent: float | None = None
    blind: bool = False


@router.get("/queue", response_model=list[CuratorQueueItem])
def list_curate_queue(
    paper_id: str | None = None,
    doc_id: int | None = None,
    bucket: str | None = None,
    version_id: str | None = None,
    benchmark_only: bool = Query(False, description="Filter for calibration benchmark units only"),
    session: Session = Depends(get_curation_db),
    account: Principal = Depends(require_account),
):
    """List pending units with suggestions for human review."""
    from caf_db.models.ingest import TagSuggestion, Unit, UnitAnswer
    from caf_db.models.ref import Node
    from caf_l0.releases import active_version, get_release
    from caf_l0.hierarchy import ancestors, version_nodes
    try:
        release = get_release(session, version_id) if version_id else active_version(session)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    taxonomy_version_id = release.taxonomy_version_id if release and release.status != "legacy" else None

    query = (
        sa.select(Unit, Document)
        .join(Document, Unit.document_id == Document.id)
        .where(
            Unit.current.is_(True),
            Unit.is_gradable.is_(True),
            Unit.classify_status == "suggested",
        )
    )

    if paper_id:
        query = query.where(Document.paper_id == paper_id)
    if doc_id:
        query = query.where(Document.id == doc_id)

    units_with_doc = session.execute(query.order_by(Document.attempt_id.desc(), Unit.id.asc())).all()

    # Pre-fetch nodes
    all_nodes = {n.id: n for n in version_nodes(session, release.taxonomy_version_id if release else None)}

    def recommendation(node_id: str) -> dict:
        node = all_nodes.get(node_id)
        ancestry = {"module": None, "chapter": None, "unit": None, "topic": None, "subtopic": None}
        current = node
        while current:
            if current.level in ancestry:
                ancestry[current.level] = {"id": current.id, "name": current.name}
            current = all_nodes.get(current.parent_id) if current.parent_id else None
        return {"node_id": node_id, "node_name": node.name if node else None, **ancestry,
                "breadcrumbs": [{"id": n.id, "name": n.name} for n in ancestors(node_id, all_nodes)]}

    items = []
    for u, doc in units_with_doc:
        is_bench = "calibration_benchmark" in (u.validation_flags or [])
        if benchmark_only and not is_bench:
            continue

        # Get suggestions
        suggs = (
            session.query(TagSuggestion)
            .filter(TagSuggestion.unit_id == u.id, TagSuggestion.is_shadow.is_(False))
            .filter(TagSuggestion.taxonomy_version_id == taxonomy_version_id)
            .order_by(TagSuggestion.id.desc())
            .all()
        )
        prim = next((s for s in suggs if s.role == "primary"), None)
        if not prim:
            continue

        if bucket and prim.bucket != bucket:
            continue

        # A primary and its secondary evidence must describe the same model run.
        secondaries = [s for s in suggs if s.role == "secondary" and s.run_id == prim.run_id
                       and s.method == prim.method and s.model_id == prim.model_id
                       and s.prompt_version == prim.prompt_version]
        ans = session.get(UnitAnswer, u.id)

        items.append(
            {
                "unit_id": u.id,
                "taxonomy_version_id": taxonomy_version_id,
                "publication_ready": False,
                "verification_state": "unknown",
                "requires_re_review": True,
                "document_id": doc.id,
                "attempt_id": doc.attempt_id,
                "paper_id": doc.paper_id,
                "doc_type_id": doc.doc_type_id,
                "label_path": u.label_path,
                "display_label": u.display_label,
                "is_benchmark": is_bench,
                "marks": u.marks,
                "question_text": u.question_text,
                "answer_text": ans.answer_text if ans else None,
                "bucket": prim.bucket,
                "primary_suggestion": {
                    **recommendation(prim.node_id),
                    "justification": (prim.evidence or {}).get("justification"),
                    "gist": (prim.evidence or {}).get("gist"),
                    "alternatives": (prim.evidence or {}).get("alternatives", []),
                    "descriptor_revision_id": prim.descriptor_revision_id,
                    "method": prim.method,
                    "model_id": prim.model_id,
                },
                "secondary_suggestions": [
                    recommendation(s.node_id)
                    for s in secondaries
                ],
            }
        )

    return items


@router.post("/units/{unit_id}/decision", response_model=CuratorDecisionResult)
def api_make_decision(
    unit_id: int,
    req: DecisionRequest,
    session: Session = Depends(get_curation_db),
    account: Principal = Depends(require_account),
):
    """Submit curator decision for an exam unit and publish to core.*."""
    from caf_l4.publish import make_decision, StaleDecisionError

    if req.action in ("bulk_accept", "undo") and account.role != "administrator":
        raise HTTPException(status_code=403, detail="Administrator capability required")
    if req.action not in ("none_fits", "exclude"):
        raise HTTPException(422, dict(code='revision_review_required',
            message='Review the complete root classification through the revision review workspace'))

    payload = {
        "primary_node_id": req.primary_node_id,
        "secondary_node_ids": req.secondary_node_ids,
        "gist": req.gist,
    }
    try:
        decision = make_decision(
            session=session,
            unit_id=unit_id,
            action=req.action,
            payload=payload,
            seconds_spent=req.seconds_spent,
            blind=req.blind,
            actor_id=account.id,
            require_pending=True,
        )
        return {
            "decision_id": decision.id,
            "action": decision.action,
            "unit_fingerprint": decision.unit_fingerprint,
        }
    except StaleDecisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/{doc_id}/bulk_accept_bucket_a", response_model=BulkAcceptResult)
def api_bulk_accept_bucket_a(
    doc_id: int,
    session: Session = Depends(get_curation_db),
    account: Principal = Depends(require_admin),
):
    """Bulk accept all remaining Bucket A suggestions for a confirmed document."""
    raise HTTPException(422, dict(code='revision_review_required',
        message='Select explicit root suggestion and publication revisions in the bulk review workspace'))


@router.post("/intel/recompute", response_model=RecomputeResult, status_code=202)
def api_curate_recompute_scores(
    target_attempt_id: str = Query(..., min_length=1),
    taxonomy_version_id: int | None = None,
    session: Session = Depends(get_operations_db),
    account: Principal = Depends(require_admin),
):
    """Queue a context-specific recomputation without blocking the request."""
    from caf_l5.jobs import enqueue_recompute

    try:
        job = enqueue_recompute(session, target_attempt_id=target_attempt_id,
                                taxonomy_version_id=taxonomy_version_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "target_attempt_id": job.target_attempt_id,
            "scoring_version": job.config_snapshot['version'],
            "taxonomy_version_id": job.taxonomy_version_id,
            "corpus_generation": job.corpus_generation,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
