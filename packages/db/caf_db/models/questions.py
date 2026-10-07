"""Immutable student publication projections and explicit occurrence identity."""
from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, Index, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from caf_db.models.base import Base


class CorpusGeneration(Base):
    __tablename__ = 'corpus_generation'
    __table_args__ = (CheckConstraint('id = 1'), {'schema': 'core'})
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')


class QuestionOccurrence(Base):
    __tablename__ = 'question_occurrence'
    __table_args__ = (CheckConstraint("identity_status IN ('confirmed','ambiguous')"), {'schema': 'core'})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    canonical_occurrence_id: Mapped[int | None] = mapped_column(ForeignKey('core.question_occurrence.id'))
    identity_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    question_id: Mapped[str] = mapped_column(Text, nullable=False)
    paper_id: Mapped[str] = mapped_column(ForeignKey('ref.paper.id'), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(ForeignKey('ref.attempt.id'))
    source_family: Mapped[str] = mapped_column(Text, nullable=False)
    signal_class: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[str | None] = mapped_column(Text)
    identity_status: Mapped[str] = mapped_column(Text, nullable=False)
    pairing_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PublishedSource(Base):
    __tablename__ = 'published_source'
    __table_args__ = {'schema': 'core'}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    doc_type_id: Mapped[str | None] = mapped_column(Text)
    attempt_id: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    approved_blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    official_url: Mapped[str | None] = mapped_column(Text)


class PublishedQuestion(Base):
    __tablename__ = 'published_question'
    __table_args__ = (Index('ix_published_question_fts', func.to_tsvector(literal_column("'english'"), literal_column('search_text')), postgresql_using='gin'), {'schema': 'core'})
    id: Mapped[int] = mapped_column(BigInteger, ForeignKey('core.classification_revision.id'), primary_key=True)
    question_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    extraction_revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey('ref.taxonomy_version.id'), nullable=False)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey('core.question_occurrence.id'), nullable=False)
    publication_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mappings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    covered_subtopics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    marks: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
