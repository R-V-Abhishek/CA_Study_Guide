"""Published student-reader/search contracts; source paths never leave the API."""
from typing import Any, Literal
from pydantic import BaseModel, Field
from caf_contracts.extraction import ExtractedQuestion, PageResult


class TaxonomyPathItem(BaseModel):
    id: str
    name: str
    level: str


class CoveredSubtopic(BaseModel):
    node_id: str
    name: str
    path: list[TaxonomyPathItem]


class PublishedSourceResult(BaseModel):
    id: int
    sha256: str
    title: str | None
    doc_type_id: str | None
    attempt_id: str | None
    page_count: int | None
    url: str
    page_url: str


class PublishedAssetResult(BaseModel):
    id: str
    source_id: int
    page: int
    kind: str
    bbox: list[float] | None = None
    concerns: list[str]
    url: str


class AttributedNodeShare(BaseModel):
    node_id: str
    share: float
    attributed_marks: float | None


class MarksAllocation(BaseModel):
    part_id: str
    marks: int | None
    allocation_status: Literal['reviewed','ambiguous']
    choice_group: str | None
    node_shares: list[AttributedNodeShare]


class PublishedMarks(BaseModel):
    whole_question_marks: int | None
    offered_marks: int | None
    selectable_marks: int | None
    allocations: list[MarksAllocation]
    issues: list[str]


class OccurrenceResult(BaseModel):
    id: int
    canonical_occurrence_id: int | None = None
    question_id: str
    paper_id: str
    attempt_id: str | None
    source_family: str
    signal_class: str
    series: str | None
    identity_status: str
    pairing_evidence: dict[str, Any]


class QuestionResult(BaseModel):
    question_id: str
    snapshot_id: int
    classification_revision_id: int
    extraction_revision_id: int
    taxonomy_version_id: int
    publication_generation: int
    content: ExtractedQuestion
    mappings: list[dict[str, Any]]
    covered_subtopics: list[CoveredSubtopic]
    marks: PublishedMarks
    sources: list[PublishedSourceResult]
    assets: list[PublishedAssetResult]
    verification_count: int
    open_disputes: int
    extraction_quality: dict[str, Any]
    occurrence: OccurrenceResult


class QuestionSummary(BaseModel):
    question_id: str
    snapshot_id: int
    paper_id: str
    attempt_id: str | None
    display_label: str
    question_text: str
    common_stem: str
    answer_status: str
    source_family: str
    covered_subtopics: list[CoveredSubtopic]


class AppearanceResolution(BaseModel):
    appearance_id: int
    question_id: str | None
    part_id: str | None
    provenance_limitation: str | None


class PrivateNoteResult(BaseModel):
    node_id: str
    content: str


class SearchResult(PageResult[QuestionSummary]):
    notes: list[PrivateNoteResult] = Field(default_factory=list)
