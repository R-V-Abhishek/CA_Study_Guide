"""Intel schema models: intel.* intelligence and scoring tables."""

from datetime import datetime
from typing import Any
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from caf_db.models.base import Base


class ScoreRun(Base):
    __tablename__ = "score_run"
    __table_args__ = (
        CheckConstraint("status IN ('running','ok','failed')", name="check_score_run_status"),
        Index(
            "one_current_run",
            "target_attempt_id", "taxonomy_version_id", "config_hash",
            unique=True,
            postgresql_where=text("is_current AND NOT shadow"),
            postgresql_nulls_not_distinct=True,
        ),
        {"schema": "intel"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    corpus_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    input_manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    target_attempt_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.attempt.id"), nullable=False)
    taxonomy_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ref.taxonomy_version.id"), nullable=True)
    shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubtopicScore(Base):
    __tablename__ = "subtopic_score"
    __table_args__ = {"schema": "intel"}

    score_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("intel.score_run.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exam_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    practice_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_prior: Mapped[float | None] = mapped_column(Float, nullable=True)
    importance: Mapped[float | None] = mapped_column(Float, nullable=True)
    freq_hits: Mapped[int] = mapped_column(Integer, nullable=False)
    freq_window: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_marks_total: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_count: Mapped[int] = mapped_column(Integer, nullable=False)
    practice_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_exam_attempt: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_exam_attempt: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionCoverage(Base):
    __tablename__ = "ingestion_coverage"
    __table_args__ = {"schema": "intel"}

    score_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("intel.score_run.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[str] = mapped_column(Text, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(Text, primary_key=True)
    exam_published: Mapped[bool] = mapped_column(Boolean, nullable=False)
    practice_published: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DepthGateReport(Base):
    __tablename__ = "depth_gate_report"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('continue','continue_practice_value','stop')",
            name="check_depth_gate_decision",
        ),
        {"schema": "intel"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_code: Mapped[str] = mapped_column(Text, nullable=False)
    band: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("intel.score_run.id"), nullable=True
    )
    shadow_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("intel.score_run.id"), nullable=True
    )
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    jaccard: Mapped[float | None] = mapped_column(Float, nullable=True)
    spearman: Mapped[float | None] = mapped_column(Float, nullable=True)
    newly_asked_nodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_to_review: Mapped[int | None] = mapped_column(Integer, nullable=True)
    est_review_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AttemptTaxonomyBinding(Base):
    __tablename__ = 'attempt_taxonomy_binding'
    __table_args__ = {'schema': 'intel'}
    target_attempt_id: Mapped[str] = mapped_column(ForeignKey('ref.attempt.id'), primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey('ref.taxonomy_version.id'), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default='pending')
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('app.user_account.id'))
    scoring_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CorpusCoverage(Base):
    __tablename__ = 'corpus_coverage'
    __table_args__ = {'schema': 'intel'}
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey('ref.taxonomy_version.id'), primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey('ref.paper.id'), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('ref.attempt.id'), primary_key=True)
    source_family: Mapped[str] = mapped_column(Text, primary_key=True)
    inventory_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_slots: Mapped[int | None] = mapped_column(Integer)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acquired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extraction_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pairing_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    official_scope_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gradable_regions_accounted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    labels_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurrence_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_roots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_roots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blockers: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class ReviewedPrior(Base):
    __tablename__ = 'reviewed_prior'
    __table_args__ = (CheckConstraint('value >= 0 AND value <= 1'), {'schema': 'intel'})
    taxonomy_version_id: Mapped[int] = mapped_column(ForeignKey('ref.taxonomy_version.id'), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey('ref.node.id'), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('app.user_account.id'))


class RecomputeJob(Base):
    __tablename__ = 'recompute_job'
    __table_args__ = (CheckConstraint("status IN ('pending','running','ok','failed')"),
        Index('uq_pending_recompute_context', 'target_attempt_id', 'taxonomy_version_id', 'config_hash', unique=True,
            postgresql_where=text("status='pending'"), postgresql_nulls_not_distinct=True), {'schema': 'intel'})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_attempt_id: Mapped[str] = mapped_column(ForeignKey('ref.attempt.id'), nullable=False)
    taxonomy_version_id: Mapped[int | None] = mapped_column(ForeignKey('ref.taxonomy_version.id'))
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    corpus_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default='pending')
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    score_run_id: Mapped[int | None] = mapped_column(ForeignKey('intel.score_run.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
