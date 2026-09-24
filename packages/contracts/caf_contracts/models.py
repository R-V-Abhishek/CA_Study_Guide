"""Pure interface contracts C0–C6 for CA Final Study Companion."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# C0: Taxonomy & Reference Contracts
# ==============================================================================

class NodeLevel(str, Enum):
    CHAPTER = "chapter"
    TOPIC = "topic"
    SUBTOPIC = "subtopic"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class SignalClass(str, Enum):
    EXAM = "exam"
    PRACTICE = "practice"
    REFERENCE = "reference"


class TaxonomyNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Opaque stable ID, e.g. P1-7KQ2MX")
    paper_id: str
    parent_id: str | None = None
    level: NodeLevel
    name: str
    seq: int
    status: NodeStatus = NodeStatus.ACTIVE
    sm_ref: str | None = None
    sm_pages: tuple[int, int] | None = None


class Descriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    approved: bool = False
    source: Literal["llm_draft", "curator"]


class Paper(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    scheme_id: str
    code: str
    name: str
    group_no: int | None = None
    max_marks: int = 100
    is_current: bool = False


class Scheme(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    notes: str | None = None


class Attempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str  # YYYY-MM
    exam_year: int
    exam_month: int
    label: str
    exam_start_date: date | None = None
    verified: bool = False


class DocType(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    signal_class: SignalClass
    has_questions: bool
    has_answers: bool
    description: str | None = None


class Anchor(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    ref_key: str
    node_id: str
    weight: float = 1.0


class WeightageSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    paper_id: str
    name: str
    min_pct: float
    max_pct: float
    valid_from_attempt: str | None = None


# ==============================================================================
# C1: Ingest Document Contracts
# ==============================================================================

class CatalogStatus(str, Enum):
    INFERRED = "inferred"
    NEEDS_CURATION = "needs_curation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ExtractStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    OK_WITH_WARNINGS = "ok_with_warnings"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class DocumentContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    sha256: str
    blob_path: str
    bytes: int
    origin: Literal["http", "browser", "assisted", "manual"]
    scheme_id: str | None = None
    attempt_id: str | None = None
    paper_id: str | None = None
    doc_type_id: str | None = None
    series: str | None = None
    part: str | None = None
    title: str | None = None
    chapter_hint_node_id: str | None = None
    catalog_status: CatalogStatus = CatalogStatus.INFERRED
    extract_status: ExtractStatus = ExtractStatus.PENDING
    page_count: int | None = None
    has_text_layer: bool | None = None


# ==============================================================================
# C2: Unit & Answer Contracts
# ==============================================================================

class UnitKind(str, Enum):
    CASE_STEM = "case_stem"
    QUESTION = "question"
    PART = "part"
    SUBPART = "subpart"
    MCQ = "mcq"


class MarksSource(str, Enum):
    EXPLICIT = "explicit"
    SUMMED = "summed"
    MCQ_DEFAULT = "mcq_default"
    OVERRIDE = "override"
    LLM_IDS = "llm_ids"


class ChoiceRole(str, Enum):
    COMPULSORY = "compulsory"
    OPTIONAL = "optional"
    UNKNOWN = "unknown"


class TextOrigin(str, Enum):
    PDF = "pdf"
    OCR = "ocr"
    LLM_TRANSCRIBED = "llm_transcribed"


class ParseConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClassifyStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUGGESTED = "suggested"
    FAILED = "failed"
    SKIPPED = "skipped"
    DECIDED = "decided"
    EXCLUDED = "excluded"


class UnitContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    document_id: int
    extract_run_id: int
    parent_unit_id: int | None = None
    label_path: str
    display_label: str
    kind: UnitKind
    is_gradable: bool
    marks: int | None = None
    marks_source: MarksSource | None = None
    choice_role: ChoiceRole | None = None
    or_group: str | None = None
    page_start: int
    page_end: int
    block_start: str
    block_end: str
    question_text: str
    text_origin: TextOrigin
    fingerprint: str
    parse_confidence: ParseConfidence
    validation_flags: list[str] = Field(default_factory=list)
    classify_status: ClassifyStatus = ClassifyStatus.PENDING
    current: bool = True


class UnitAnswerContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit_id: int
    answer_document_id: int
    answer_text: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    mcq_correct_option: str | None = None
    pairing_method: Literal["same_doc", "cross_doc", "mcq_key", "override"]


# ==============================================================================
# C3: Suggestion & Gist Contracts
# ==============================================================================

class SuggestionRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class SuggestionMethod(str, Enum):
    STRUCTURE = "structure"
    ANCHOR = "anchor"
    LLM = "llm"
    DUPLICATE = "duplicate"


class SuggestionBucket(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class TagSuggestionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    unit_id: int
    run_id: int
    node_id: str
    role: SuggestionRole
    method: SuggestionMethod
    bucket: SuggestionBucket
    evidence: dict[str, Any]
    model_id: str | None = None
    prompt_version: str | None = None
    is_shadow: bool = False


class UnitGistContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    unit_id: int
    run_id: int
    gist: str = Field(max_length=220)
    model_id: str | None = None


# ==============================================================================
# C4: Published Knowledge Contracts
# ==============================================================================

class AppearanceStatus(str, Enum):
    PUBLISHED = "published"
    ORPHANED = "orphaned"
    WITHDRAWN = "withdrawn"


class AppearanceContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None
    unit_fingerprint: str
    source_unit_id: int | None = None
    doc_sha256: str
    attempt_id: str
    source_paper_id: str
    doc_type_id: str
    signal_class: Literal["exam", "practice"]
    series: str | None = None
    display_label: str
    marks: int | None = None
    gist: str
    official_url: str | None = None
    official_url_dead: bool = False
    page_start: int
    page_end: int
    law_stale: bool = False
    status: AppearanceStatus = AppearanceStatus.PUBLISHED
    duplicate_of: int | None = None


class AppearanceTagContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    appearance_id: int
    node_id: str
    role: SuggestionRole
    share: float
    decision_id: int


# ==============================================================================
# C5: Intelligence Scores Contracts
# ==============================================================================

class SubtopicScoreContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    score_run_id: int
    node_id: str
    applicable: bool
    exam_score: float
    practice_score: float
    weight_prior: float
    importance: float
    freq_hits: int
    freq_window: int
    exam_marks_total: int
    exam_count: int
    practice_count: int
    first_exam_attempt: str | None = None
    last_exam_attempt: str | None = None


class IngestionCoverageContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    score_run_id: int
    paper_id: str
    attempt_id: str
    exam_published: bool
    practice_published: bool


# ==============================================================================
# C6: API & Study State Contracts
# ==============================================================================

class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ProgressContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: int
    node_id: str
    status: ProgressStatus
    notes: str | None = None
    updated_at: datetime
    completed_at: datetime | None = None
