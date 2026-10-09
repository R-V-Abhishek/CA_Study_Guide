"""Textbook provenance and release review contracts."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    artifact_id: str
    pdf_page_start: int = Field(ge=1)
    pdf_page_end: int = Field(ge=1)
    review_status: Literal["pending", "reviewed"] = "pending"

    @model_validator(mode="after")
    def ordered(self):
        if self.pdf_page_end < self.pdf_page_start:
            raise ValueError("Source page range is reversed")
        return self


class DescriptorContent(StrictModel):
    definition: str = Field(min_length=1)
    terminology: list[str] = Field(default_factory=list)
    instrument_references: list[str] = Field(default_factory=list)
    edition: str | None = None
    source_ambiguities: list[str] = Field(default_factory=list)
    inclusion: list[str] = Field(default_factory=list)
    exclusion: list[str] = Field(default_factory=list)
    nearby_distinctions: list[str] = Field(default_factory=list)
    source_spans: list[SourceSpan] = Field(min_length=1)


class ReleaseApproval(StrictModel):
    manifest_hash: str


class ReleaseActivation(ReleaseApproval):
    dry_run: bool = True


class DescriptorEdit(DescriptorContent):
    version_id: str


class DescriptorReview(StrictModel):
    version_id: str
    revision: int = Field(ge=1)


class SourceReview(StrictModel):
    version_id: str


class CrosswalkReview(StrictModel):
    version_id: str


class ReleaseSummary(BaseModel):
    version_id: str
    taxonomy_version_id: int
    target_attempt: str
    status: str
    manifest_hash: str
    approved_by: int | None
    activated_at: str | None


class TaxonomyTreeNode(BaseModel):
    id: str
    paper_id: str
    parent_id: str | None
    level: str
    name: str
    seq: int
    heading_origin: str = "official"
    source_review_status: str
    descriptor_revision: int | None
    descriptor_approved: bool
    eligible: bool
    status: Literal['not_started', 'in_progress', 'done'] | None = None
    breadcrumbs: list[dict[str, str]]
    sources: list[dict[str, Any]]
    children: list["TaxonomyTreeNode"] = Field(default_factory=list)
