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
