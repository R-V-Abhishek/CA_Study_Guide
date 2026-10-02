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
    doc = session.get(Document, doc_id)
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
    benchmark_only: bool = Query(False, description="Filter for calibration benchmark units only"),
    session: Session = Depends(get_curation_db),
    account: Principal = Depends(require_account),
):
    """List pending units with suggestions for human review."""
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

    def recommendation(node_id: str) -> dict:
        node = all_nodes.get(node_id)
        ancestry = {"chapter": None, "topic": None, "subtopic": None}
        current = node
        while current:
            if current.level in ancestry:
                ancestry[current.level] = {"id": current.id, "name": current.name}
            current = all_nodes.get(current.parent_id) if current.parent_id else None
        return {"node_id": node_id, "node_name": node.name if node else None, **ancestry}

    items = []
    for u, doc in units_with_doc:
        is_bench = "calibration_benchmark" in (u.validation_flags or [])
        if benchmark_only and not is_bench:
            continue

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
    from caf_l4.publish import bulk_accept_bucket_a, StaleDecisionError

    try:
        count = bulk_accept_bucket_a(session, doc_id, actor_id=account.id)
        return {"document_id": doc_id, "accepted_count": count}
    except StaleDecisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/intel/recompute", response_model=RecomputeResult)
def api_curate_recompute_scores(
    target_attempt_id: str = Query(..., min_length=1),
    shadow: bool = False,
    session: Session = Depends(get_operations_db),
    account: Principal = Depends(require_admin),
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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
