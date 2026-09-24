"""L1 Catalogue confirmation and curation logic."""

from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.logging import get_logger
from caf_db.models.ingest import Document
from caf_db.models.ref import Attempt, Paper

logger = get_logger("acquire.catalog")


def list_pending_documents(
    session: Session,
    attempt_id: str | None = None,
    paper_id: str | None = None,
) -> list[Document]:
    query = sa.select(Document).where(
        Document.catalog_status.in_(["inferred", "needs_curation"]),
        Document.superseded.is_(False),
    ).order_by(Document.id.desc())

    if attempt_id:
        query = query.where(Document.attempt_id == attempt_id)
    if paper_id:
        query = query.where(Document.paper_id == paper_id)

    return session.execute(query).scalars().all()


def confirm_document(
    session: Session,
    doc_id: int,
    overrides: dict[str, Any] | None = None,
) -> Document:
    doc = session.get(Document, doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    if overrides:
        for k, v in overrides.items():
            if hasattr(doc, k) and v is not None:
                setattr(doc, k, v)

    # Validation against ref
    if not doc.attempt_id or not session.get(Attempt, doc.attempt_id):
        raise ValueError(f"Invalid or missing attempt: {doc.attempt_id}")
    if not doc.paper_id or not session.get(Paper, doc.paper_id):
        raise ValueError(f"Invalid or missing paper: {doc.paper_id}")
    if not doc.doc_type_id:
        raise ValueError("Missing doc_type_id")

    doc.catalog_status = "confirmed"
    session.commit()
    logger.info("document_confirmed", id=doc.id, title=doc.title)
    return doc


def reject_document(session: Session, doc_id: int, reason: str = "curator_rejected") -> Document:
    doc = session.get(Document, doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    doc.catalog_status = "rejected"
    session.commit()
    logger.info("document_rejected", id=doc.id, reason=reason)
    return doc
