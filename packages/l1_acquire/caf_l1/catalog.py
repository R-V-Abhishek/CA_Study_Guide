"""L1 Catalogue confirmation and curation logic."""

from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.logging import get_logger
from caf_db.models.ingest import Document
from caf_db.models.ref import Attempt, DocType, Paper

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
        allowed = {"attempt_id", "paper_id", "doc_type_id", "series", "part", "title", "course_level"}
        if set(overrides) - allowed:
            raise ValueError("Unknown catalogue override fields")
        for k, v in overrides.items():
            setattr(doc, k, v)

    # Validation against ref
    undated_model = doc.doc_type_id in {"model_question", "model_answer"} and doc.attempt_id is None
    if not undated_model and (not doc.attempt_id or not session.get(Attempt, doc.attempt_id)):
        raise ValueError(f"Invalid or missing attempt: {doc.attempt_id}")
    if not doc.paper_id or not session.get(Paper, doc.paper_id):
        raise ValueError(f"Invalid or missing paper: {doc.paper_id}")
    if not doc.doc_type_id:
        raise ValueError("Missing doc_type_id")
    if not session.get(DocType, doc.doc_type_id):
        raise ValueError(f"Unknown document type: {doc.doc_type_id}")
    if doc.course_level in {"foundation", "intermediate"}:
        raise ValueError("Lower-level sources belong outside the Final corpus")
    paper = session.get(Paper, doc.paper_id)
    if paper.scheme_id != doc.scheme_id:
        raise ValueError("Source scheme does not match its paper")

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
