"""App schema models: app.* user progress, settings, and notes."""

from datetime import date, datetime
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from caf_db.models.base import Base


class UserAccount(Base):
    __tablename__ = "user_account"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Settings(Base):
    __tablename__ = "settings"
    __table_args__ = {"schema": "app"}

    user_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("app.user_account.id"), primary_key=True
    )
    target_attempt_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.attempt.id"), nullable=True
    )
    exam_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hours_per_week: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=20.0)
    minutes_per_subtopic: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    revision_intervals: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [3, 7, 21, 60]
    )


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started','in_progress','done')", name="check_progress_status"
        ),
        {"schema": "app"},
    )

    user_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("app.user_account.id"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    first_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_revised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verify_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProgressEvent(Base):
    __tablename__ = "progress_event"
    __table_args__ = (
        Index("ix_app_progress_event_user_at", "user_id", "at"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Note(Base):
    __tablename__ = "note"
    __table_args__ = {"schema": "app"}

    user_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("app.user_account.id"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RevisionEvent(Base):
    __tablename__ = "revision_event"
    __table_args__ = (
        CheckConstraint("outcome IN ('ok','shaky')", name="check_revision_outcome"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MockTest(Base):
    __tablename__ = "mock_test"
    __table_args__ = (
        CheckConstraint("max_score > 0", name="check_mock_test_max_score"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    paper_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("ref.attempt.id"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    taken_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudySession(Base):
    __tablename__ = "study_session"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    node_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
