"""Curator API endpoints for document review and catalog confirmation."""

from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_api.routes import get_db
from caf_l1.catalog import confirm_document, reject_document
from caf_db.models.ingest import Document

router = APIRouter(prefix="/api/v1/curate", tags=["curation"])


class DocumentEditRequest(BaseModel):
    attempt_id: str | None = None
    paper_id: str | None = None
    doc_type_id: str | None = None
    series: str | None = None
    part: str | None = None
    title: str | None = None


class DocumentConfirmRequest(BaseModel):
    attempt_id: str | None = None
    paper_id: str | None = None
    doc_type_id: str | None = None
    series: str | None = None
    part: str | None = None
    title: str | None = None


@router.get("/documents")
def list_curate_documents(
    status: str | None = Query(None, description="inferred, needs_curation, confirmed, rejected"),
    attempt_id: str | None = None,
    paper_id: str | None = None,
    session: Session = Depends(get_db),
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


@router.post("/documents/{doc_id}/confirm")
def api_confirm_document(
    doc_id: int,
    req: DocumentConfirmRequest | None = None,
    session: Session = Depends(get_db),
):
    overrides = req.model_dump(exclude_unset=True) if req else None
    try:
        doc = confirm_document(session, doc_id, overrides=overrides)
        return {
            "id": doc.id,
            "catalog_status": doc.catalog_status,
            "attempt_id": doc.attempt_id,
            "paper_id": doc.paper_id,
            "doc_type_id": doc.doc_type_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/{doc_id}/reject")
def api_reject_document(doc_id: int, session: Session = Depends(get_db)):
    try:
        doc = reject_document(session, doc_id)
        return {"id": doc.id, "catalog_status": doc.catalog_status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/documents/{doc_id}")
def api_edit_document(
    doc_id: int,
    req: DocumentEditRequest,
    session: Session = Depends(get_db),
):
    doc = session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        if hasattr(doc, k) and v is not None:
            setattr(doc, k, v)

    session.commit()
    return {"id": doc.id, "title": doc.title, "catalog_status": doc.catalog_status}


# ==============================================================================
# Tag Review Queue & Curation Decisions
# ==============================================================================

class DecisionRequest(BaseModel):
    action: str  # accept | accept_alt | edit | none_fits | exclude | bulk_accept | undo
    primary_node_id: str | None = None
    secondary_node_ids: list[str] = []
    gist: str | None = None
    seconds_spent: float | None = None
    blind: bool = False


@router.get("/queue")
def list_curate_queue(
    paper_id: str | None = None,
    doc_id: int | None = None,
    bucket: str | None = None,
    session: Session = Depends(get_db),
):
    """List pending units with suggestions for human review."""
    from caf_db.models.core import Decision
    from caf_db.models.ingest import TagSuggestion, Unit, UnitAnswer
    from caf_db.models.ref import Node

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
    all_nodes = {n.id: n for n in session.query(Node).all()}

    items = []
    for u, doc in units_with_doc:
        # Get suggestions
        suggs = (
            session.query(TagSuggestion)
            .filter(TagSuggestion.unit_id == u.id, TagSuggestion.is_shadow.is_(False))
            .all()
        )
        prim = next((s for s in suggs if s.role == "primary"), None)
        if not prim:
            continue

        if bucket and prim.bucket != bucket:
            continue

        secondaries = [s for s in suggs if s.role == "secondary"]
        ans = session.get(UnitAnswer, u.id)

        items.append(
            {
                "unit_id": u.id,
                "document_id": doc.id,
                "attempt_id": doc.attempt_id,
                "paper_id": doc.paper_id,
                "doc_type_id": doc.doc_type_id,
                "label_path": u.label_path,
                "display_label": u.display_label,
                "marks": u.marks,
                "question_text": u.question_text,
                "answer_text": ans.answer_text if ans else None,
                "bucket": prim.bucket,
                "primary_suggestion": {
                    "node_id": prim.node_id,
                    "node_name": all_nodes.get(prim.node_id, Node(name=prim.node_id)).name,
                    "justification": prim.evidence.get("justification") if isinstance(prim.evidence, dict) else None,
                    "gist": prim.evidence.get("gist") if isinstance(prim.evidence, dict) else None,
                    "alternatives": prim.evidence.get("alternatives", []) if isinstance(prim.evidence, dict) else [],
                },
                "secondary_suggestions": [
                    {
                        "node_id": s.node_id,
                        "node_name": all_nodes.get(s.node_id, Node(name=s.node_id)).name,
                    }
                    for s in secondaries
                ],
            }
        )

    return items


@router.post("/units/{unit_id}/decision")
def api_make_decision(
    unit_id: int,
    req: DecisionRequest,
    session: Session = Depends(get_db),
):
    """Submit curator decision for an exam unit and publish to core.*."""
    from caf_l4.publish import make_decision

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
        )
        return {
            "decision_id": decision.id,
            "action": decision.action,
            "unit_fingerprint": decision.unit_fingerprint,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/{doc_id}/bulk_accept_bucket_a")
def api_bulk_accept_bucket_a(
    doc_id: int,
    session: Session = Depends(get_db),
):
    """Bulk accept all remaining Bucket A suggestions for a confirmed document."""
    from caf_l4.publish import bulk_accept_bucket_a

    try:
        count = bulk_accept_bucket_a(session, doc_id)
        return {"document_id": doc_id, "accepted_count": count}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/intel/recompute")
def api_curate_recompute_scores(
    target_attempt_id: str | None = None,
    shadow: bool = False,
    session: Session = Depends(get_db),
):
    """Trigger an L5 intelligence score recomputation."""
    from caf_l5 import recompute_scores

    try:
        run = recompute_scores(session, target_attempt_id=target_attempt_id, shadow=shadow)
        return {
            "run_id": run.id,
            "status": run.status,
            "target_attempt_id": run.target_attempt_id,
            "scoring_version": run.scoring_version,
            "is_current": run.is_current,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
