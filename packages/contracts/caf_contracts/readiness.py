"""Administrator readiness decisions, with source-bound and optimistic writes."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TextbookEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['textbook_span']
    span_id: int = Field(ge=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class DocumentEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['document_revision']
    revision_id: int = Field(ge=1)
    content_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    pdf_page_start: int = Field(ge=1)
    pdf_page_end: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.pdf_page_end < self.pdf_page_start:
            raise ValueError('Source page range must be ordered')
        return self


SourceEvidence = Annotated[TextbookEvidence | DocumentEvidence, Field(discriminator='kind')]


class ReadinessWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence: Nonblank = Field(max_length=10000)
    idempotency_key: Nonblank = Field(max_length=200)
    taxonomy_version_id: int = Field(ge=1)
    source_evidence: list[SourceEvidence] = Field(min_length=1, max_length=100)


class BindingWrite(ReadinessWrite):
    target_attempt_id: Nonblank
    action: Literal['review', 'withdraw']


class InventoryWrite(ReadinessWrite):
    paper_id: Nonblank
    attempt_id: Nonblank
    source_family: Nonblank
    expected_slots: int | None = Field(ge=0)


class PriorWrite(ReadinessWrite):
    node_id: Nonblank
    value: float = Field(ge=0, le=1, allow_inf_nan=False)


class BindingRecord(BaseModel):
    target_attempt_id: str
    taxonomy_version_id: int
    status: str
    reviewed_by: int | None
    expected_hash: str


class InventoryRecord(BaseModel):
    taxonomy_version_id: int
    paper_id: str
    attempt_id: str
    source_family: str
    expected_slots: int | None
    inventory_reviewed: bool
    expected_hash: str


class PriorRecord(BaseModel):
    taxonomy_version_id: int
    node_id: str
    value: float | None
    reviewed_by: int | None
    expected_hash: str


class AffectedRecord(BaseModel):
    kind: str
    id: str
    revision: str | None = None


class ReadinessAction(BaseModel):
    label: str
    href: str


class ReadinessTask(BaseModel):
    id: str
    paper_id: str | None
    stage: int
    stage_name: str
    blocker: str
    evidence: list[str]
    required_role: str
    next_action: ReadinessAction
    affected_records: list[AffectedRecord]


class PaperReadiness(BaseModel):
    paper_id: str
    name: str
    blocker_count: int
    published_roots: int
    expected_slots: int | None


class AuditDecision(BaseModel):
    id: int
    actor_id: int
    action: str
    evidence: str
    created_at: datetime
    record_id: str
    before_hash: str
    after_hash: str


class ReadinessSummary(BaseModel):
    target_attempt_id: str
    taxonomy_version_id: int | None
    papers: list[PaperReadiness]
    tasks: list[ReadinessTask]
    bindings: list[BindingRecord]
    inventory: list[InventoryRecord]
    priors: list[PriorRecord]
    source_evidence: list[SourceEvidence]
    history: list[AuditDecision]


class ReadinessWriteResult(BaseModel):
    record_id: str
    expected_hash: str
    audit_id: int
    actor_id: int
    corpus_generation: int
