"""Immutable root classifications and authenticated collaborative review history."""

from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from caf_db.models.base import Base


class SuggestionRevision(Base):
    __tablename__ = "suggestion_revision"
    __table_args__ = (UniqueConstraint("batch_key", "question_id", "input_hash"), {"schema": "ingest"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_key: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("ingest.document.id"), nullable=False)
    extraction_revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("ref.taxonomy_version.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("ops.run.id"), nullable=False)
    experimental: Mapped[bool] = mapped_column(Boolean, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    mappings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationRevision(Base):
    __tablename__ = "classification_revision"
    __table_args__ = {"schema": "core"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    suggestion_revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.suggestion_revision.id"), nullable=False)
    extraction_revision_id: Mapped[int] = mapped_column(ForeignKey("ingest.extraction_revision.id"), nullable=False)
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey("ref.taxonomy_version.id"), nullable=False)
    previous_revision_id: Mapped[int | None] = mapped_column(ForeignKey("core.classification_revision.id"))
    mappings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), nullable=False)
    blind: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuestionPublication(Base):
    __tablename__ = "question_publication"
    __table_args__ = {"schema": "core"}
    question_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("ingest.document.id"), nullable=False)
    current_revision_id: Mapped[int | None] = mapped_column(ForeignKey("core.classification_revision.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationEvent(Base):
    __tablename__ = "classification_event"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"), {"schema": "core"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[int | None] = mapped_column(ForeignKey("core.classification_revision.id"))
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationVerification(Base):
    __tablename__ = "classification_verification"
    __table_args__ = (UniqueConstraint("revision_id", "actor_id"), {"schema": "core"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("core.classification_revision.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationDispute(Base):
    __tablename__ = "classification_dispute"
    __table_args__ = (CheckConstraint("status IN ('open','dismissed','replaced')"), {"schema": "core"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision_id: Mapped[int] = mapped_column(ForeignKey("core.classification_revision.id"), nullable=False)
    proposed_revision_id: Mapped[int | None] = mapped_column(ForeignKey("core.classification_revision.id"))
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app.user_account.id"))
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
