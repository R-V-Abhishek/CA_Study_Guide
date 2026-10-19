"""Runtime, unpublished whole-question and extraction-review contracts."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from caf_contracts.future_v1 import CompleteQuestionV1

QualityDimension = Literal['metadata','questions','answers','pairing','ordering','marks_choices','readability','human_review']
QualityStatus = Literal['pending','passed','concern','not_applicable']


class PaperPageRange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    paper_id: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.page_end < self.page_start:
            raise ValueError('Paper page range must be ordered')
        return self


class QuestionChoice(BaseModel):
    label: str
    role: str
    or_group: str | None
    marks: int | None


class QuestionMCQ(BaseModel):
    part_id: str
    options: list[str]
    key: str | None


class AnswerPairingCandidate(BaseModel):
    answer_doc_id: int | None
    label_path: str
    answer_text: str | None
    page_start: int | None
    page_end: int | None
    block_start: str | None
    block_end: str | None
    mcq_correct_option: str | None


class PartPairingCandidates(BaseModel):
    part_id: str
    label_path: str
    status: Literal['matched','missing','partial','ambiguous']
    candidates: list[AnswerPairingCandidate]


class QuestionAsset(BaseModel):
    document_id: int
    page: int
    kind: str
    bbox: list[float] | None = None
    concerns: list[str]


class ExtractedQuestion(CompleteQuestionV1):
    label_path: str
    course_level: str | None
    scheme_id: str
    source_family: str
    source_collection_id: str | None = None
    question_status: Literal['complete','partial','unknown'] = 'unknown'
    readability_status: QualityStatus = 'pending'
    pairing_status: Literal['matched','missing','partial','ambiguous','not_expected']
    review_status: Literal['pending','reviewed'] = 'pending'
    choices: list[QuestionChoice] = Field(default_factory=list)
    mcq: list[QuestionMCQ] = Field(default_factory=list)
    assets: list[QuestionAsset] = Field(default_factory=list)
    source_document_ids: list[int] = Field(default_factory=list)
    pairing_candidates: list[PartPairingCandidates] = Field(default_factory=list)


class ExtractionMetadataEvidence(BaseModel):
    model_config = ConfigDict(extra='allow')
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionDocument(BaseModel):
    id: int
    title: str | None
    sha256: str
    course_level: str | None
    scheme_id: str | None
    paper_id: str | None
    attempt_id: str | None
    collection_id: str | None
    doc_type_id: str | None
    catalog_status: str
    extract_status: str
    page_count: int | None
    current_revision_id: int | None
    paper_page_ranges: list[PaperPageRange] = Field(default_factory=list)
    metadata_evidence: ExtractionMetadataEvidence = Field(default_factory=ExtractionMetadataEvidence)


class RevisionSummary(BaseModel):
    id: int
    document_id: int
    base_revision_id: int | None
    status: str
    content_digest: str
    profile_id: str
    quality: dict[str, Any]
    created_at: str


class RevisionDetail(RevisionSummary):
    configuration: dict[str, Any]
    questions: list[ExtractedQuestion]
    source_documents: list[dict[str, Any]] = Field(default_factory=list)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label_path: str
    reason: str = Field(min_length=1, max_length=10000)
    question_text: str | None = None
    answer_text: str | None = None
    answer_candidate_label: str | None = Field(default=None,min_length=1,max_length=1000)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    block_start: str | None = None
    block_end: str | None = None
    marks: int | None = Field(default=None, ge=0, le=100)
    is_gradable: bool | None = Field(default=None, strict=True)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dimension: QualityDimension
    status: QualityStatus
    note: str = Field(min_length=1, max_length=10000)


class ReviewResult(BaseModel):
    id: int
    revision_id: int
    actor_id: int
    content_digest: str
    dimension: str
    status: str
    note: str


class PromoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_current_revision_id: int | None


class PromoteResult(BaseModel):
    id: int
    document_id: int
    status: str
    current_revision_id: int
    units: int


class PairRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_document_id: int
    evidence: str = Field(min_length=1, max_length=10000)


class PairResult(BaseModel):
    id: int
    question_document_id: int
    answer_document_id: int
    status: str
    evidence: dict[str, Any]


class ReconciliationResult(BaseModel):
    id: int
    revision_id: int
    old_unit_id: int | None
    new_label: str | None
    relation: str
    evidence: dict[str, Any]


class BlockResult(BaseModel):
    id: int
    revision_id: int
    block_key: str
    sequence: int
    page: int
    bbox: list[float]
    raw_text: str
    normalized_text: str
    origin: str


class AssetResult(BaseModel):
    id: int
    revision_id: int
    page: int
    kind: str
    bbox: list[float] | None
    concerns: list[str]


class PageResult[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
