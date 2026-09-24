"""Ingest schema models: ingest.* tables."""

from datetime import datetime
from typing import Any
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from caf_db.models.base import Base


class SourcePage(Base):
    __tablename__ = "source_page"
    __table_args__ = (
        CheckConstraint(
            "fetch_mode IN ('http','browser','assisted')", name="check_source_page_fetch_mode"
        ),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_page_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingest.source_page.id"), nullable=True
    )
    fetch_mode: Mapped[str] = mapped_column(Text, nullable=False)
    robots_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('http','browser','assisted','manual')", name="check_document_origin"
        ),
        CheckConstraint(
            "catalog_status IN ('inferred','needs_curation','confirmed','rejected')",
            name="check_document_catalog_status",
        ),
        CheckConstraint(
            "extract_status IN ('pending','running','ok','ok_with_warnings','needs_review','failed','not_applicable')",
            name="check_document_extract_status",
        ),
        Index("ix_ingest_document_catalog_extract", "catalog_status", "extract_status"),
        Index("ix_ingest_document_attempt_paper_type", "attempt_id", "paper_id", "doc_type_id"),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    scheme_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.scheme.id"), nullable=True)
    attempt_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.attempt.id"), nullable=True)
    paper_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=True)
    doc_type_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.doc_type.id"), nullable=True
    )
    series: Mapped[str | None] = mapped_column(Text, nullable=True)
    part: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapter_hint_node_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.node.id"), nullable=True
    )
    catalog_status: Mapped[str] = mapped_column(Text, nullable=False, default="inferred")
    extract_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    extract_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), nullable=True
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_text_layer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ocr_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supersedes_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingest.document.id"), nullable=True
    )
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    depth_band: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DiscoveredLink(Base):
    __tablename__ = "discovered_link"
    __table_args__ = (
        CheckConstraint(
            "link_status IN ('new','downloaded','failed','manual_required','ignored','not_pdf')",
            name="check_link_status",
        ),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_page_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingest.source_page.id"), nullable=True
    )
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    breadcrumb: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    inferred: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    link_status: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingest.document.id"), nullable=True
    )
    tries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_try_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Unit(Base):
    __tablename__ = "unit"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('case_stem','question','part','subpart','mcq')",
            name="check_unit_kind",
        ),
        CheckConstraint(
            "marks IS NULL OR marks BETWEEN 0 AND 100",
            name="check_unit_marks",
        ),
        CheckConstraint(
            "marks_source IN ('explicit','summed','mcq_default','override','llm_ids')",
            name="check_unit_marks_source",
        ),
        CheckConstraint(
            "choice_role IN ('compulsory','optional','unknown')",
            name="check_unit_choice_role",
        ),
        CheckConstraint(
            "text_origin IN ('pdf','ocr','llm_transcribed')",
            name="check_unit_text_origin",
        ),
        CheckConstraint(
            "parse_confidence IN ('high','medium','low')",
            name="check_unit_parse_confidence",
        ),
        CheckConstraint(
            "classify_status IN ('pending','running','suggested','failed','skipped','decided','excluded')",
            name="check_unit_classify_status",
        ),
        UniqueConstraint("document_id", "extract_run_id", "label_path", name="uq_unit_doc_run_label"),
        Index("ix_ingest_unit_fingerprint", "fingerprint"),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.document.id"), nullable=False
    )
    extract_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), nullable=False
    )
    parent_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), nullable=True
    )
    label_path: Mapped[str] = mapped_column(Text, nullable=False)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    is_gradable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marks_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    choice_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    or_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    block_start: Mapped[str] = mapped_column(Text, nullable=False)
    block_end: Mapped[str] = mapped_column(Text, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_origin: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)
    parse_confidence: Mapped[str] = mapped_column(Text, nullable=False)
    validation_flags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    classify_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UnitAnswer(Base):
    __tablename__ = "unit_answer"
    __table_args__ = (
        CheckConstraint(
            "pairing_method IN ('same_doc','cross_doc','mcq_key','override')",
            name="check_pairing_method",
        ),
        {"schema": "ingest"},
    )

    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), primary_key=True
    )
    answer_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.document.id"), nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mcq_correct_option: Mapped[str | None] = mapped_column(String(1), nullable=True)
    pairing_method: Mapped[str] = mapped_column(Text, nullable=False)


class TagSuggestion(Base):
    __tablename__ = "tag_suggestion"
    __table_args__ = (
        CheckConstraint("role IN ('primary','secondary')", name="check_suggestion_role"),
        CheckConstraint("method IN ('structure','anchor','llm','duplicate')", name="check_suggestion_method"),
        CheckConstraint("bucket IN ('A','B','C','D')", name="check_suggestion_bucket"),
        Index("ix_ingest_tag_suggestion_unit_shadow", "unit_id", "is_shadow"),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), nullable=False
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    bucket: Mapped[str] = mapped_column(String(1), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UnitGist(Base):
    __tablename__ = "unit_gist"
    __table_args__ = (
        CheckConstraint("char_length(gist) <= 220", name="check_gist_length"),
        {"schema": "ingest"},
    )

    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), primary_key=True
    )
    gist: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxonomyGap(Base):
    __tablename__ = "taxonomy_gap"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open','resolved_new_node','resolved_existing','ignored')",
            name="check_gap_status",
        ),
        {"schema": "ingest"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ops.run.id"), nullable=True
    )
    proposed_parent_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.node.id"), nullable=True
    )
    proposed_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")


class DuplicateLink(Base):
    __tablename__ = "duplicate_link"
    __table_args__ = {"schema": "ingest"}

    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), primary_key=True
    )
    other_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingest.unit.id"), primary_key=True
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
