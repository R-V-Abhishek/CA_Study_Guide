"""Operational models: ops.run, ops.llm_call, ops.event."""

from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from caf_db.models.base import Base


class Run(Base):
    __tablename__ = "run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','ok','partial','failed','aborted_budget')",
            name="check_run_status",
        ),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_calls: Mapped[list["LLMCall"]] = relationship("LLMCall", back_populates="run")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="run")


class LLMCall(Base):
    __tablename__ = "llm_call"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','retry','schema_error','error')",
            name="check_llm_call_status",
        ),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.run.id"), nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 5), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    batch_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="llm_calls")


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "level IN ('info','warn','error','alarm')",
            name="check_event_level",
        ),
        {"schema": "ops"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ops.run.id"), nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["Run"] = relationship("Run", back_populates="events")
