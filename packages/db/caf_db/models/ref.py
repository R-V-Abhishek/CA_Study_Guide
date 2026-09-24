"""Reference schema models: ref.* tables."""

from datetime import date, datetime
from typing import Any
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INT4RANGE
from sqlalchemy.orm import Mapped, mapped_column, relationship

from caf_db.models.base import Base


class TaxonomyVersion(Base):
    __tablename__ = "taxonomy_version"
    __table_args__ = {"schema": "ref"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    yaml_hash: Mapped[str] = mapped_column(Text, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Scheme(Base):
    __tablename__ = "scheme"
    __table_args__ = {"schema": "ref"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    papers: Mapped[list["Paper"]] = relationship("Paper", back_populates="scheme")


class Attempt(Base):
    __tablename__ = "attempt"
    __table_args__ = (
        CheckConstraint("exam_month BETWEEN 1 AND 12", name="check_exam_month"),
        UniqueConstraint("exam_year", "exam_month", name="uq_attempt_year_month"),
        {"schema": "ref"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # YYYY-MM
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_month: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    exam_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Paper(Base):
    __tablename__ = "paper"
    __table_args__ = (
        UniqueConstraint("scheme_id", "code", name="uq_paper_scheme_code"),
        {"schema": "ref"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # e.g. s2023.P1
    scheme_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.scheme.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    group_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    scheme: Mapped["Scheme"] = relationship("Scheme", back_populates="papers")
    nodes: Mapped[list["Node"]] = relationship("Node", back_populates="paper")


class DocType(Base):
    __tablename__ = "doc_type"
    __table_args__ = (
        CheckConstraint(
            "signal_class IN ('exam','practice','reference')", name="check_doc_type_signal_class"
        ),
        {"schema": "ref"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    signal_class: Mapped[str] = mapped_column(Text, nullable=False)
    has_questions: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_answers: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Node(Base):
    __tablename__ = "node"
    __table_args__ = (
        CheckConstraint(
            "level IN ('chapter','topic','subtopic')", name="check_node_level"
        ),
        CheckConstraint(
            "status IN ('active','deprecated')", name="check_node_status"
        ),
        CheckConstraint(
            "((level = 'chapter') = (parent_id IS NULL))", name="check_chapter_parent_null"
        ),
        Index("ix_ref_node_parent_id", "parent_id"),
        Index("ix_ref_node_paper_id_level", "paper_id", "level"),
        {"schema": "ref"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # P1-7KQ2MX
    paper_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    sm_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    sm_pages: Mapped[Any | None] = mapped_column(INT4RANGE, nullable=True)
    created_in: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ref.taxonomy_version.id"), nullable=True
    )
    updated_in: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ref.taxonomy_version.id"), nullable=True
    )

    paper: Mapped["Paper"] = relationship("Paper", back_populates="nodes")
    descriptor: Mapped["Descriptor | None"] = relationship("Descriptor", back_populates="node", uselist=False)


class Descriptor(Base):
    __tablename__ = "descriptor"
    __table_args__ = (
        CheckConstraint("source IN ('llm_draft','curator')", name="check_descriptor_source"),
        {"schema": "ref"},
    )

    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)

    node: Mapped["Node"] = relationship("Node", back_populates="descriptor")


class Instrument(Base):
    __tablename__ = "instrument"
    __table_args__ = {"schema": "ref"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    paper_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)


class Anchor(Base):
    __tablename__ = "anchor"
    __table_args__ = (
        UniqueConstraint("instrument_id", "ref_key", "node_id", name="uq_anchor_inst_ref_node"),
        Index("ix_ref_anchor_lookup", "instrument_id", "ref_key"),
        {"schema": "ref"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.instrument.id"), nullable=False)
    ref_key: Mapped[str] = mapped_column(Text, nullable=False)
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class WeightageSection(Base):
    __tablename__ = "weightage_section"
    __table_args__ = {"schema": "ref"}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    min_pct: Mapped[float] = mapped_column(Numeric, nullable=False)
    max_pct: Mapped[float] = mapped_column(Numeric, nullable=False)
    valid_from_attempt: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.attempt.id"), nullable=True
    )


class WeightageMember(Base):
    __tablename__ = "weightage_member"
    __table_args__ = {"schema": "ref"}

    section_id: Mapped[str] = mapped_column(
        Text, ForeignKey("ref.weightage_section.id"), primary_key=True
    )
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)


class ApplicabilityRule(Base):
    __tablename__ = "applicability_rule"
    __table_args__ = (
        CheckConstraint("effect IN ('exclude','include')", name="check_applicability_effect"),
        {"schema": "ref"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.attempt.id"), nullable=False)
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    effect: Mapped[str] = mapped_column(Text, nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LawBoundary(Base):
    __tablename__ = "law_boundary"
    __table_args__ = (
        CheckConstraint("policy IN ('mark_stale','exclude')", name="check_law_boundary_policy"),
        {"schema": "ref"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_code: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.instrument.id"), nullable=True
    )
    first_applicable_attempt: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.attempt.id"), nullable=True
    )
    scope_node_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    policy: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class NodeVersionLink(Base):
    __tablename__ = "node_version_link"
    __table_args__ = (
        CheckConstraint(
            "relation IN ('split_into','merged_into','moved')",
            name="check_version_link_relation",
        ),
        {"schema": "ref"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    old_node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    new_node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ref.taxonomy_version.id"), nullable=False
    )
