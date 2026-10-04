"""L1 Catalogue confirmation and curation logic."""

from typing import Any
from datetime import datetime, timezone
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
    *, actor_id: int | None = None,
) -> Document:
    doc = session.scalar(sa.select(Document).where(Document.id==doc_id).with_for_update().execution_options(populate_existing=True))
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    if overrides:
        allowed = {"attempt_id", "paper_id", "doc_type_id", "series", "part", "title", "course_level",
                   "collection_id", "paper_page_ranges", "scheme_id"}
        if set(overrides) - allowed:
            raise ValueError("Unknown catalogue override fields")
        for k, v in overrides.items():
            setattr(doc, k, v)

    # Validation against ref
    undated_collection = doc.attempt_id is None and (doc.doc_type_id in {"model_question", "model_answer"}
                                                   or (doc.doc_type_id in {"case_scenarios", "ibs_case_study"} and doc.collection_id))
    if not undated_collection and (not doc.attempt_id or not session.get(Attempt, doc.attempt_id)):
        raise ValueError(f"Invalid or missing attempt: {doc.attempt_id}")
    ranges = doc.paper_page_ranges or []
    if not ranges and (not doc.paper_id or not session.get(Paper, doc.paper_id)):
        raise ValueError(f"Invalid or missing paper: {doc.paper_id}")
    if not doc.doc_type_id:
        raise ValueError("Missing doc_type_id")
    if not session.get(DocType, doc.doc_type_id):
        raise ValueError(f"Unknown document type: {doc.doc_type_id}")
    if doc.course_level in {"foundation", "intermediate"}:
        raise ValueError("Lower-level sources belong outside the Final corpus")
    if doc.course_level != "final":
        raise ValueError("Confirm course_level=final before including a source in the Final corpus")
    covered = set()
    paper_ids = [doc.paper_id] if doc.paper_id else []
    for span in ranges:
        first, last = span["page_start"], span["page_end"]
        if first < 1 or last < first or doc.page_count is None or last > doc.page_count:
            raise ValueError("Paper page range outside document bounds")
        pages = set(range(first, last + 1))
        if covered & pages:
            raise ValueError("Overlapping paper page ranges")
        covered |= pages
        paper_ids.append(span["paper_id"])
    for paper_id in paper_ids:
        paper = session.get(Paper, paper_id)
        if not paper or paper.scheme_id != doc.scheme_id:
            raise ValueError("Source scheme does not match its paper")
    evidence = doc.metadata_evidence or {}
    doc.metadata_evidence = {**evidence, "conflicts":[], "administrator_confirmation": {
        "actor_id":actor_id,
        "confirmed_at": datetime.now(timezone.utc).isoformat(), "overrides": overrides or {},
        "resolved_conflicts": evidence.get("conflicts", [])}}

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
