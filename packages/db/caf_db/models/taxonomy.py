"""Immutable textbook releases and independently reviewed classification context."""

from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from caf_db.models.base import Base


class TaxonomyRelease(Base):
    __tablename__ = "taxonomy_release"
    __table_args__ = (Index("one_active_taxonomy_release", "status", unique=True, postgresql_where=text("status='active'")), {"schema": "ref"})
    version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.taxonomy_version.id"), unique=True)
    target_attempt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app.user_account.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_review_hash: Mapped[str | None] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaxonomyMember(Base):
    __tablename__ = "taxonomy_member"
    __table_args__ = (
        ForeignKeyConstraint(["taxonomy_version_id", "parent_id"], ["ref.taxonomy_member.taxonomy_version_id", "ref.taxonomy_member.node_id"], name="fk_taxonomy_member_parent", deferrable=True, initially="DEFERRED"),
        {"schema": "ref"},
    )
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.taxonomy_version.id"), primary_key=True)
    node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.paper.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_origin: Mapped[str] = mapped_column(Text, nullable=False, default="official")


class TextbookArtifact(Base):
    __tablename__ = "textbook_artifact"
    __table_args__ = {"schema": "ref"}
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.taxonomy_version.id"), primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text, nullable=False)
    course_level: Mapped[str] = mapped_column(Text, nullable=False)
    edition: Mapped[str] = mapped_column(Text, nullable=False)
    availability: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class NodeSourceSpan(Base):
    __tablename__ = "node_source_span"
    __table_args__ = (
        ForeignKeyConstraint(["taxonomy_version_id", "node_id"], ["ref.taxonomy_member.taxonomy_version_id", "ref.taxonomy_member.node_id"]),
        ForeignKeyConstraint(["taxonomy_version_id", "artifact_id"], ["ref.textbook_artifact.taxonomy_version_id", "ref.textbook_artifact.id"]),
        {"schema": "ref"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_id: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    pdf_page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app.user_account.id"))


class DescriptorRevision(Base):
    __tablename__ = "descriptor_revision"
    __table_args__ = (
        UniqueConstraint("taxonomy_version_id", "node_id", "revision"),
        ForeignKeyConstraint(["taxonomy_version_id", "node_id"], ["ref.taxonomy_member.taxonomy_version_id", "ref.taxonomy_member.node_id"]),
        {"schema": "ref"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app.user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DescriptorApproval(Base):
    __tablename__ = "descriptor_approval"
    __table_args__ = {"schema": "ref"}
    revision_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.descriptor_revision.id"), primary_key=True)
    approved_by: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxonomyCrosswalk(Base):
    __tablename__ = "taxonomy_crosswalk"
    __table_args__ = {"schema": "ref"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxonomy_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.taxonomy_version.id"), nullable=False)
    old_node_id: Mapped[str] = mapped_column(Text, ForeignKey("ref.node.id"), nullable=False)
    new_node_id: Mapped[str | None] = mapped_column(Text, ForeignKey("ref.node.id"))
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app.user_account.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProgressMigration(Base):
    __tablename__ = "progress_migration"
    __table_args__ = {"schema": "app"}
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app.user_account.id"), primary_key=True)
    crosswalk_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref.taxonomy_crosswalk.id"), primary_key=True)
    migrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    original_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
