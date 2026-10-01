"""Shared-study contract draft, version 1; no endpoint or ORM bindings.

The existing ``caf_contracts.models`` contracts remain the current runtime contract.
These models describe future C0/C2/C4/C5/C6 payloads; validating a payload does not
authenticate its caller, authorize access, or publish database content.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class FutureContractV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["shared-study.v1"] = "shared-study.v1"


class SourceSpanV1(FutureContractV1):
    document_sha256: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    block_start: str | None = None
    block_end: str | None = None
    official_url: str | None = None

    @model_validator(mode="after")
    def ordered_pages(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("Source span pages must be ordered")
        return self


# C0: Official hierarchy, including paper-specific module/unit exceptions.
class TaxonomyNodeV1(FutureContractV1):
    id: str = Field(min_length=1)
    paper_id: str
    parent_id: str | None
    level: Literal["module", "chapter", "unit", "topic", "subtopic"]
    name: str
    sequence: int = Field(ge=0)
    stable_path: tuple[str, ...] = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    source_spans: tuple[SourceSpanV1, ...] = Field(min_length=1)
    applicability_reference_ids: tuple[str, ...] = Field(min_length=1)
    source_structure_note: str | None = None

    @model_validator(mode="after")
    def path_matches_identity(self) -> Self:
        if self.stable_path[-1] != self.id:
            raise ValueError("Stable path must end at this node")
        expected_parent = self.stable_path[-2] if len(self.stable_path) > 1 else None
        if expected_parent != self.parent_id:
            raise ValueError("Stable path must identify this node's parent")
        return self


# C2: Root/common stem and ordered, independently classifiable parts and answers.
class QuestionPartV1(FutureContractV1):
    id: str
    label: str
    sequence: int = Field(ge=0)
    question_text: str
    marks: int | None = Field(default=None, ge=0)
    source_spans: tuple[SourceSpanV1, ...] = Field(min_length=1)
    parts: tuple["QuestionPartV1", ...] = ()

    @model_validator(mode="after")
    def ordered_parts(self) -> Self:
        _validate_order(self.parts)
        return self


class AnswerPartV1(FutureContractV1):
    id: str
    question_part_id: str | None = None
    sequence: int = Field(ge=0)
    answer_text: str
    source_spans: tuple[SourceSpanV1, ...] = Field(min_length=1)
    parts: tuple["AnswerPartV1", ...] = ()

    @model_validator(mode="after")
    def ordered_parts(self) -> Self:
        _validate_order(self.parts)
        return self


def _validate_order(parts: tuple[QuestionPartV1, ...] | tuple[AnswerPartV1, ...]) -> None:
    sequences = [part.sequence for part in parts]
    if sequences != sorted(set(sequences)):
        raise ValueError("Parts must have unique, increasing sequence values")


class CompleteQuestionV1(FutureContractV1):
    question_id: str = Field(min_length=1)
    content_revision: str = Field(min_length=1)
    paper_id: str
    source_attempt_id: str
    display_label: str
    common_stem: str
    question_text: str
    parts: tuple[QuestionPartV1, ...] = ()
    answers: tuple[AnswerPartV1, ...] = ()
    answer_status: Literal["complete", "partial", "missing"]
    source_spans: tuple[SourceSpanV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        _validate_order(self.parts)
        _validate_order(self.answers)
        if (self.answer_status == "missing") != (not self.answers):
            raise ValueError("Answer status must agree with available answer parts")
        question_ids = {self.question_id}

        def collect(parts: tuple[QuestionPartV1, ...]) -> None:
            for part in parts:
                if part.id in question_ids:
                    raise ValueError("Question part IDs must be unique within the root")
                question_ids.add(part.id)
                collect(part.parts)

        def check_answers(parts: tuple[AnswerPartV1, ...]) -> None:
            for part in parts:
                if part.question_part_id and part.question_part_id not in question_ids:
                    raise ValueError("Answer must refer to a part in this complete question")
                check_answers(part.parts)

        collect(self.parts)
        check_answers(self.answers)
        return self


# C4: Reviewer identities belong to exact content/classification revisions.
class PublishedRevisionV1(FutureContractV1):
    question_id: str
    content_revision: str = Field(min_length=1)
    classification_revision: str = Field(min_length=1)


class VerificationScopeV1(str, Enum):
    CONTENT = "content"
    CLASSIFICATION = "classification"
    CONTENT_AND_CLASSIFICATION = "content_and_classification"


class StudentReviewV1(FutureContractV1):
    reviewer_student_id: str = Field(min_length=1)
    revision: PublishedRevisionV1
    scope: VerificationScopeV1
    reviewed_at: datetime


class PublishedKnowledgeV1(FutureContractV1):
    revision: PublishedRevisionV1
    published_by_student_id: str = Field(min_length=1)
    published_at: datetime
    classified_node_ids: tuple[str, ...] = Field(min_length=1)
    taxonomy_version: str
    reviews: tuple[StudentReviewV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def revision_bound_reviews(self) -> Self:
        for review in self.reviews:
            if review.revision != self.revision:
                raise ValueError("Review applies to a different published revision")
        if not any(
            review.reviewer_student_id == self.published_by_student_id
            and review.scope in (
                VerificationScopeV1.CLASSIFICATION,
                VerificationScopeV1.CONTENT_AND_CLASSIFICATION,
            )
            for review in self.reviews
        ):
            raise ValueError("Publication requires its student's classification review")
        return self

    @computed_field
    @property
    def content_verification_count(self) -> int:
        return self._count_reviewers(VerificationScopeV1.CONTENT)

    @computed_field
    @property
    def classification_verification_count(self) -> int:
        return self._count_reviewers(VerificationScopeV1.CLASSIFICATION)

    def _count_reviewers(self, scope: VerificationScopeV1) -> int:
        return len({
            review.reviewer_student_id
            for review in self.reviews
            if review.scope in (scope, VerificationScopeV1.CONTENT_AND_CLASSIFICATION)
        })


# C5: Raw units are independent from normalized components and configured weights.
class ScoreContextV1(FutureContractV1):
    target_attempt_id: str
    taxonomy_version: str
    material_applicability_version: str
    scoring_version: str
    published_corpus_revision: str


class ScoreComponentV1(FutureContractV1):
    raw_value: float = Field(ge=0, allow_inf_nan=False)
    raw_unit: Literal["decayed_marks", "marks"]
    normalized_value: float = Field(ge=0, le=1, allow_inf_nan=False)
    weight: float = Field(ge=0, le=1, allow_inf_nan=False)


class ScoreSnapshotV1(FutureContractV1):
    score_run_id: int
    node_id: str
    context: ScoreContextV1
    exam: ScoreComponentV1
    practice: ScoreComponentV1
    weight_prior: ScoreComponentV1
    importance: float = Field(ge=0, le=1, allow_inf_nan=False)
    computed_at: datetime
    source_updated_at: datetime
    freshness: Literal["fresh", "stale", "recompute_pending"]

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> Self:
        if abs(self.exam.weight + self.practice.weight + self.weight_prior.weight - 1) > 1e-9:
            raise ValueError("Score component weights must sum to one")
        return self


# C6: Explicit authenticated ownership and published-response boundaries.
class AuthenticatedStudentV1(FutureContractV1):
    student_id: str = Field(min_length=1)
    authentication_subject: str = Field(min_length=1)
    invited: Literal[True]
    can_curate: Literal[True] = True


class PrivateStudyRecordV1(FutureContractV1):
    owner_student_id: str = Field(min_length=1)
    node_id: str
    progress: Literal["not_started", "in_progress", "done"]
    notes: str
    target_attempt_id: str = "2027-05"
    updated_at: datetime


class PrivateStudyResponseV1(FutureContractV1):
    authenticated_student: AuthenticatedStudentV1
    record: PrivateStudyRecordV1

    @model_validator(mode="after")
    def owner_matches_authenticated_student(self) -> Self:
        if self.record.owner_student_id != self.authenticated_student.student_id:
            raise ValueError("Private response belongs to a different authenticated student")
        return self


class PublishedContentResponseV1(FutureContractV1):
    authenticated_student: AuthenticatedStudentV1
    visibility: Literal["published"] = "published"
    publication: PublishedKnowledgeV1
    question: CompleteQuestionV1

    @model_validator(mode="after")
    def published_content_matches_revision(self) -> Self:
        revision = self.publication.revision
        if (
            self.question.question_id != revision.question_id
            or self.question.content_revision != revision.content_revision
        ):
            raise ValueError("Response content must match its published revision")
        return self
