"""Immutable extraction candidates, source evidence and revision-bound reviews."""

from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, Integer, Text, String, ForeignKey, DateTime, UniqueConstraint, CheckConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from caf_db.models.base import Base


class ExtractionRevision(Base):
    __tablename__ = "extraction_revision"
    __table_args__ = (
        UniqueConstraint("document_id", "content_digest", name="uq_extraction_content"),
        CheckConstraint("status IN ('candidate','current','superseded','failed')", name="check_revision_status"),
        Index('uq_current_extraction_revision', 'document_id', unique=True, postgresql_where=text("status='current'")),
        {"schema": "ingest"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ingest.document.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("ops.run.id"), nullable=False)
    base_revision_id: Mapped[int | None] = mapped_column(ForeignKey("ingest.extraction_revision.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_id: Mapped[str] = mapped_column(Text, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    parsed_units: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app.user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentBlock(Base):
    __tablename__ = "content_block"
    __table_args__ = (UniqueConstraint("revision_id", "block_key"), {"schema": "ingest"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    block_key: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)


class ExtractionAsset(Base):
    __tablename__ = "extraction_asset"
    __table_args__ = {"schema": "ingest"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSONB)
    concerns: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class DocumentPair(Base):
    __tablename__ = "document_pair"
    __table_args__ = (UniqueConstraint("question_document_id", "answer_document_id"), {"schema": "ingest"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_document_id: Mapped[int] = mapped_column(ForeignKey("ingest.document.id"), nullable=False)
    answer_document_id: Mapped[int] = mapped_column(ForeignKey("ingest.document.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("app.user_account.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractionReview(Base):
    __tablename__ = "extraction_review"
    __table_args__ = {"schema": "ingest"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("app.user_account.id"), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReconciliationLink(Base):
    __tablename__ = "reconciliation_link"
    __table_args__ = {"schema": "ingest"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    old_unit_id: Mapped[int | None] = mapped_column(ForeignKey("ingest.unit.id"))
    new_label: Mapped[str | None] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
