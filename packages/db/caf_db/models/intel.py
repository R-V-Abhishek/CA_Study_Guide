"""Intel schema models: intel.* intelligence and scoring tables."""

from datetime import datetime
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
            "is_current",
            unique=True,
            postgresql_where=text("is_current AND NOT shadow"),
        ),
        {"schema": "intel"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    target_attempt_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.attempt.id"), nullable=False)
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
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exam_score: Mapped[float] = mapped_column(Float, nullable=False)
    practice_score: Mapped[float] = mapped_column(Float, nullable=False)
    weight_prior: Mapped[float] = mapped_column(Float, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
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
