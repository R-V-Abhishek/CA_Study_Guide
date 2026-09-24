"""Core schema models: core.* published knowledge tables."""

from datetime import datetime
from typing import Any
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from caf_db.models.base import Base


class Appearance(Base):
    __tablename__ = "appearance"
    __table_args__ = (
        CheckConstraint(
            "signal_class IN ('exam','practice')", name="check_appearance_signal_class"
        ),
        CheckConstraint(
            "status IN ('published','orphaned','withdrawn')", name="check_appearance_status"
        ),
        Index(
            "ix_core_appearance_attempt_signal",
            "attempt_id",
            "signal_class",
            postgresql_where=text("status = 'published'"),
        ),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_fingerprint: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    source_unit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    doc_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.attempt.id"), nullable=False)
    source_paper_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=False)
    doc_type_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.doc_type.id"), nullable=False)
    signal_class: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gist: Mapped[str] = mapped_column(Text, nullable=False)
    official_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_url_dead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    law_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="published")
    duplicate_of: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core.appearance.id"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[list["AppearanceTag"]] = relationship(
        "AppearanceTag", back_populates="appearance", cascade="all, delete-orphan"
    )


class AppearanceTag(Base):
    __tablename__ = "appearance_tag"
    __table_args__ = (
        CheckConstraint("role IN ('primary','secondary')", name="check_app_tag_role"),
        CheckConstraint("share > 0 AND share <= 1", name="check_app_tag_share"),
        Index("ix_core_appearance_tag_node", "node_id"),
        {"schema": "core"},
    )

    appearance_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core.appearance.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    share: Mapped[float] = mapped_column(Float, nullable=False)
    decision_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    appearance: Mapped["Appearance"] = relationship("Appearance", back_populates="tags")


class Decision(Base):
    __tablename__ = "decision"
    __table_args__ = (
        CheckConstraint(
            "action IN ('accept','accept_alt','edit','none_fits','exclude','bulk_accept','undo')",
            name="check_decision_action",
        ),
        Index("ix_core_decision_fingerprint_date", "unit_fingerprint", "decided_at"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    unit_fingerprint: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    suggestion_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    blind: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seconds_spent: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChangeLog(Base):
    __tablename__ = "change_log"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    change: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
