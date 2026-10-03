"""API response contracts. OpenAPI and the generated web client derive from these models."""

from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field
from caf_contracts.taxonomy import TaxonomyTreeNode


class NodeReference(BaseModel):
    id: str
    name: str


class PaperReference(NodeReference):
    code: str


class ScoreRunIdentity(BaseModel):
    id: int
    version: str
    target_attempt_id: str
    taxonomy_version_id: int | None = None
    computed_at: datetime | None


class PaperTree(BaseModel):
    paper_id: str
    code: str
    name: str
    chapters: list['ChapterItem']
    taxonomy_version_id: int | None = None
    hierarchy: list[TaxonomyTreeNode] = Field(default_factory=list)


class SubtopicItem(BaseModel):
    id: str
    name: str
    seq: int
    status: Literal['not_started', 'in_progress', 'done']
    notes: str | None
    first_done_at: datetime | None
    last_revised_at: datetime | None
    importance: float | None
    freq_hits: int
    freq_window: int
    weak: bool
    applicable: bool


class TopicItem(BaseModel):
    id: str
    name: str
    seq: int
    subtopics: list[SubtopicItem]


class ChapterItem(BaseModel):
    id: str
    name: str
    seq: int
    weightage_min_pct: float | None
    weightage_max_pct: float | None
    weightage_section_name: str | None
    total_subtopics: int
    completed_subtopics: int
    progress_pct: float
    topics: list[TopicItem]


class PaperSummary(BaseModel):
    id: str
    code: str
    name: str
    group_no: int | None
    total_subtopics: int
    completed_subtopics: int
    raw_progress_pct: float
    weighted_coverage_pct: float | None
    average_importance: float | None
    revision_due_count: int
    weak_topic_count: int


class PlanItem(BaseModel):
    node_id: str
    node_name: str
    paper_id: str
    paper_code: str
    chapter_id: str
    chapter_name: str
    status: Literal['not_started', 'in_progress', 'done']
    importance: float
    priority_score: float
    weak: bool
    freq_hits: int
    freq_window: int
    exam_marks_total: int
    reason: str


class StudyPlan(BaseModel):
    score_unavailable_reason: str | None = None
    budget_items: int
    total_allocated: int
    hours_per_week: float
    minutes_per_subtopic: int
    items: list[PlanItem]


class RevisionItem(BaseModel):
    node_id: str
    node_name: str
    paper_id: str
    paper_code: str
    importance: float | None
    due_date: date
    overdue_days: int
    revision_count_k: int
    interval_days: int
    first_done_at: datetime | None
    last_revised_at: datetime | None


class RevisionQueue(BaseModel):
    total_due: int
    items: list[RevisionItem]


class WeakSubtopic(BaseModel):
    node_id: str
    node_name: str
    paper_id: str
    paper_code: str
    importance: float
    freq_hits: int
    freq_window: int
    exam_marks_total: int
    exam_count: int
    status: Literal['not_started', 'in_progress', 'done']


class CoverageValue(BaseModel):
    coverage_pct: float | None
    in_progress_pct: float | None


class PaperCoverage(CoverageValue):
    code: str


class WeightedCoverage(BaseModel):
    overall_coverage_pct: float | None
    overall_in_progress_pct: float | None
    groups: dict[int, CoverageValue]
    papers: dict[str, PaperCoverage]


class IngestionCoverageItem(BaseModel):
    paper_id: str
    attempt_id: str
    exam_published: bool
    practice_published: bool


class ActivityItem(BaseModel):
    node_id: str
    node_name: str
    paper_code: str
    from_status: str
    to_status: str
    at: datetime


class Dashboard(BaseModel):
    score_unavailable_reason: str | None = None
    target_attempt: str
    score_run_id: int | None
    total_subtopics: int
    done_subtopics: int
    in_progress_subtopics: int
    overall_progress_pct: float
    group1_progress_pct: float
    group2_progress_pct: float
    weighted_coverage: WeightedCoverage
    weak_subtopics: list[WeakSubtopic]
    ingestion_coverage: list[IngestionCoverageItem]
    plan_preview: list[PlanItem]
    revision_due_count: int
    recent_activity: list[ActivityItem]


class Metadata(BaseModel):
    score_unavailable_reason: str | None = None
    taxonomy_version: str
    scoring_version: str | None
    api_version: str
    backend_revision: str
    target_attempt: str
    score_run_id: int | None
    score_run_computed_at: datetime | None
    score_run: ScoreRunIdentity | None
    ingestion_coverage: list[IngestionCoverageItem]


class Weightage(BaseModel):
    section_name: str
    min_pct: float
    max_pct: float


class AppearanceItem(BaseModel):
    id: int
    attempt_id: str
    signal_class: str
    display_label: str
    marks: int | None
    gist: str | None
    official_url: str | None
    page_start: int | None
    page_end: int | None
    law_stale: bool


class SubtopicScoreDetail(BaseModel):
    importance: float | None
    exam_score: float | None
    practice_score: float | None
    weight_prior: float | None
    freq_hits: int
    freq_window: int
    exam_marks_total: int
    exam_count: int
    practice_count: int
    first_exam_attempt: str | None
    last_exam_attempt: str | None
    weak: bool
    applicable: bool


class SubtopicDetail(BaseModel):
    id: str
    name: str
    paper: PaperReference | None
    chapter: NodeReference | None
    topic: NodeReference | None
    status: Literal['not_started', 'in_progress', 'done']
    notes: str | None
    status_changed_at: datetime | None
    first_done_at: datetime | None
    last_revised_at: datetime | None
    weightage: Weightage | None
    score_run: ScoreRunIdentity | None
    score: SubtopicScoreDetail
    appearances: list[AppearanceItem]


class ExplanationSubtopic(BaseModel):
    id: str
    name: str
    paper: PaperReference | None
    chapter: NodeReference | None
    topic: NodeReference | None
    applicable: bool


class ExplanationWeights(BaseModel):
    exam: float
    practice: float
    prior: float


class ExamSignal(BaseModel):
    score_E: float
    paper_max_E: float
    normalized_E_hat: float
    normalized_E_pct: float
    weighted_contribution: float | None
    weighted_contribution_pct: float | None


class PracticeSignal(BaseModel):
    score_P: float
    paper_max_P: float
    normalized_P_hat: float
    normalized_P_pct: float
    weighted_contribution: float | None
    weighted_contribution_pct: float | None


class PriorSignal(BaseModel):
    available: bool = True
    unavailable_reason: str | None = None
    weight_prior_W: float
    paper_max_W: float
    normalized_W_hat: float
    normalized_W_pct: float
    weighted_contribution: float | None
    weighted_contribution_pct: float | None


class ImportanceBreakdown(BaseModel):
    importance: float | None
    weights: ExplanationWeights | None
    exam: ExamSignal | None
    practice: PracticeSignal | None
    weightage_prior: PriorSignal | None


class FrequencyExplanation(BaseModel):
    freq_hits_F: int
    freq_window: int
    window_attempts: list[str]
    hit_attempts: list[str]


class WeightageExplanation(Weightage):
    section_id: str
    midpoint_pct: float
    section_marks: float
    applicable_subtopics_in_section: int
    subtopic_weight_prior_W: float


class AppearanceExplanation(BaseModel):
    appearance_id: int
    attempt_id: str
    signal_class: str
    display_label: str
    gist: str | None
    marks: int | None
    tag_role: str
    tag_level: str
    share: float
    kappa: float
    lambda_val: float
    attributed_marks_m: float
    age_months: int
    half_life_months: float
    decay: float
    contribution: float
    in_freq_window: bool
    ignored_post_target: bool
    law_stale: bool


class ScoreExplanation(BaseModel):
    node_id: str
    explanation_status: Literal['available', 'historical_configuration_unavailable', 'score_unavailable', 'no_score_run']
    error: str | None
    configuration_source: Literal['snapshot', 'matching_current'] | None
    score_run: ScoreRunIdentity | None
    subtopic: ExplanationSubtopic
    importance_breakdown: ImportanceBreakdown
    frequency: FrequencyExplanation | None
    weightage_section: WeightageExplanation | None
    appearances: list[AppearanceExplanation]


class ProgressResult(BaseModel):
    status: Literal['not_started', 'in_progress', 'done']
    node_id: str
    updated_at: datetime


class NoteResult(BaseModel):
    node_id: str
    notes: str
    updated_at: datetime


class RevisionResult(BaseModel):
    event_id: int
    node_id: str
    outcome: Literal['ok', 'shaky']
    at: datetime
    last_revised_at: datetime


class MockTestResult(BaseModel):
    id: int
    paper_id: str
    paper_code: str
    attempt_id: str | None
    label: str | None
    score: float
    max_score: float
    score_pct: float
    taken_on: date
    notes: str | None


class DeleteResult(BaseModel):
    deleted: bool
    id: int


class CuratorRecommendation(BaseModel):
    node_id: str
    node_name: str | None
    chapter: NodeReference | None
    topic: NodeReference | None
    subtopic: NodeReference | None
    module: NodeReference | None = None
    unit: NodeReference | None = None
    breadcrumbs: list[NodeReference] = Field(default_factory=list)
    descriptor_revision_id: int | None = None
    method: str | None = None
    model_id: str | None = None
    justification: str | None = None
    gist: str | None = None
    alternatives: list[str] = Field(default_factory=list)


class CuratorQueueItem(BaseModel):
    unit_id: int
    taxonomy_version_id: int | None = None
    publication_ready: bool = True
    document_id: int
    attempt_id: str | None
    paper_id: str | None
    doc_type_id: str | None
    label_path: str
    display_label: str
    is_benchmark: bool
    marks: int | None
    question_text: str
    answer_text: str | None
    bucket: str
    primary_suggestion: CuratorRecommendation
    secondary_suggestions: list[CuratorRecommendation]


class CuratorDecisionResult(BaseModel):
    decision_id: int
    action: str
    unit_fingerprint: str


class CuratorDocument(BaseModel):
    id: int
    sha256: str
    course_level: Literal["foundation", "intermediate", "final"] | None = None
    provenance_status: Literal["synthetic", "unresolved", "verified"] = "unresolved"
    title: str | None
    scheme_id: str | None
    attempt_id: str | None
    paper_id: str | None
    doc_type_id: str | None
    series: str | None
    part: str | None
    catalog_status: str
    extract_status: str
    page_count: int | None
    bytes: int
    origin: str
    created_at: datetime | None


class DocumentConfirmResult(BaseModel):
    id: int
    catalog_status: str
    attempt_id: str | None
    paper_id: str | None
    doc_type_id: str | None


class DocumentStatusResult(BaseModel):
    id: int
    catalog_status: str


class DocumentEditResult(BaseModel):
    id: int
    title: str | None
    catalog_status: str


class BulkAcceptResult(BaseModel):
    document_id: int
    accepted_count: int


class RecomputeResult(BaseModel):
    run_id: int
    status: str
    target_attempt_id: str
    scoring_version: str
    is_current: bool


class SystemAlarm(BaseModel):
    code: str
    level: str
    message: str
    details: dict[str, Any]


class SystemHealth(BaseModel):
    status: str
    evaluated_at: datetime
    alarms: list[SystemAlarm]


class BackupItem(BaseModel):
    name: str
    path: str
    size_mb: float
    age_hours: float
    created_at: datetime


class BackupList(BaseModel):
    count: int
    backups: list[BackupItem]


class BackupResult(BaseModel):
    status: str
    dump_file: str
    size_bytes: int
    blobs_copied: int
    configs_copied: int
    created_at: datetime


class BucketMetric(BaseModel):
    bucket: str
    total: int
    matched: int
    precision: float


class ModelEvaluation(BaseModel):
    total_reviewed: int
    top1_matches: int
    top1_agreement: float
    bucket_metrics: dict[str, BucketMetric]
    bucket_a_threshold: float
    passed: bool
    status_note: str
    evaluated_at: datetime


class ProfilePaper(BaseModel):
    id: str
    code: str
    name: str
    group_no: int


class ProfileAttempt(BaseModel):
    id: str
    label: str


class ProfileSettings(BaseModel):
    display_name: str
    target_attempt_id: str
    selected_paper_ids: list[str]
    groups: list[int]
    hours_per_week: float
    minutes_per_subtopic: int
    revision_intervals: list[int]
    exam_start_date: date | None
    available_papers: list[ProfilePaper]
    available_attempts: list[ProfileAttempt]


class ExportProgress(BaseModel):
    node_id: str
    status: str
    status_changed_at: datetime
    first_done_at: datetime | None
    last_revised_at: datetime | None
    verify_flag: bool


class ExportNote(BaseModel):
    node_id: str
    body: str
    updated_at: datetime


class ExportProgressEvent(BaseModel):
    id: int
    node_id: str
    from_status: str | None
    to_status: str
    at: datetime


class ExportRevisionEvent(BaseModel):
    id: int
    node_id: str
    outcome: str
    at: datetime


class ExportStudySession(BaseModel):
    id: int
    node_id: str | None
    started_at: datetime
    ended_at: datetime | None
    minutes: int | None


class ProfileExport(BaseModel):
    account_id: int
    exported_at: datetime
    settings: ProfileSettings
    progress: list[ExportProgress]
    notes: list[ExportNote]
    progress_events: list[ExportProgressEvent]
    revision_events: list[ExportRevisionEvent]
    mock_tests: list[MockTestResult]
    study_sessions: list[ExportStudySession]
