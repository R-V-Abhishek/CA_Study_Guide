"""Whole-question classification and authenticated revision-review contracts."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from caf_contracts.extraction import ExtractedQuestion


class PartMapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    part_id: str = Field(min_length=1)
    outcome: Literal['matched', 'needs_review', 'none_fits']
    primary_node_id: str | None = None
    secondary_node_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    bucket: str | None = None
    excluded: bool = False

    @model_validator(mode='after')
    def consistent_labels(self):
        if self.excluded or self.outcome != 'matched':
            if self.primary_node_id or self.secondary_node_ids:
                raise ValueError('Unresolved or excluded parts cannot carry labels')
        elif not self.primary_node_id:
            raise ValueError('Matched parts require a primary label')
        if len(set(self.secondary_node_ids)) != len(self.secondary_node_ids):
            raise ValueError('Secondary labels must be distinct')
        if self.primary_node_id in self.secondary_node_ids:
            raise ValueError('Primary label cannot also be secondary')
        return self


class RevisionExpectation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_suggestion_revision_id: int = Field(ge=1)
    expected_publication_revision_id: int | None
    idempotency_key: str = Field(min_length=1, max_length=200)


class ClassificationReviewRequest(RevisionExpectation):
    mappings: list[PartMapping] = Field(min_length=1)
    note: str = Field(min_length=1, max_length=10000)
    blind: bool = False

    @model_validator(mode='after')
    def distinct_parts(self):
        if len({part.part_id for part in self.mappings}) != len(self.mappings):
            raise ValueError('Each part must appear exactly once')
        return self


class ClassificationVerificationRequest(RevisionExpectation):
    pass


class ClassificationDisputeRequest(RevisionExpectation):
    reason: str = Field(min_length=1, max_length=10000)
    replacement_mappings: list[PartMapping] | None = None


class ClassificationResolveRequest(RevisionExpectation):
    resolution: Literal['dismiss', 'replace']
    reason: str = Field(min_length=1, max_length=10000)
    replacement_mappings: list[PartMapping] | None = None

    @model_validator(mode='after')
    def replacement_required(self):
        if self.resolution == 'replace' and not self.replacement_mappings:
            raise ValueError('Replacement resolution requires the complete mapping')
        return self


class ClassificationRevisionResult(BaseModel):
    revision_id: int | None = None
    current_revision_id: int | None = None
    verification_count: int = 0
    pending: bool = False
    dispute_id: int | None = None
    status: str | None = None


class ClassificationHistoryItem(BaseModel):
    id: int
    suggestion_revision_id: int
    document_id: int
    question_id: str
    mappings: list[PartMapping]
    status: str
    actor_id: int
    created_at: datetime
    verification_count: int
    note: str | None = None


class ClassificationDisputeResult(BaseModel):
    id: int
    classification_revision_id: int
    status: str
    reason: str


class ReadinessBlocker(BaseModel):
    code: str
    message: str


class ClassificationQueueItem(BaseModel):
    suggestion_revision_id: int
    document_id: int
    question_id: str
    extraction_revision_id: int
    taxonomy_version_id: int
    run_id: int | None
    input_hash: str
    paper_id: str | None
    attempt_id: str | None
    doc_type_id: str | None
    experimental: bool
    stale: bool
    publication_ready: bool
    readiness_blockers: list[ReadinessBlocker]
    question: ExtractedQuestion
    mappings: list[PartMapping]
    candidates: list[dict[str, Any]]
    candidate_catalog_hash: str | None = None
    provenance: dict[str, Any]
    publication_revision_id: int | None
    publication_suggestion_revision_id: int | None = None
    published_mappings: list[PartMapping] = Field(default_factory=list)
    published_question: ExtractedQuestion | None = None
    verification_count: int | None
    verified_by_me: bool = False
    dispute_status: str | None
    is_benchmark: bool = False
    blind: bool = False


class ClassificationBulkRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reviews: list[ClassificationReviewRequest] = Field(min_length=1, max_length=100)


class ClassificationBulkResult(BaseModel):
    revisions: list[ClassificationRevisionResult]
