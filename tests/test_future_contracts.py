"""Pure future contracts: representability and validation, without auth or DB I/O."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from caf_contracts.future_v1 import (
    AuthenticatedStudentV1,
    CompleteQuestionV1,
    PrivateStudyRecordV1,
    PrivateStudyResponseV1,
    PublishedContentResponseV1,
    PublishedKnowledgeV1,
    PublishedRevisionV1,
    ScoreComponentV1,
    ScoreContextV1,
    ScoreSnapshotV1,
    SourceSpanV1,
    StudentReviewV1,
    TaxonomyNodeV1,
    VerificationScopeV1,
)


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
SPAN = SourceSpanV1(document_sha256="a" * 64, page_start=1, page_end=2)
REVISION = PublishedRevisionV1(
    question_id="q1", content_revision="content-2", classification_revision="classification-3"
)


def review(student_id, scope=VerificationScopeV1.CONTENT_AND_CLASSIFICATION, revision=REVISION):
    return StudentReviewV1(
        reviewer_student_id=student_id, revision=revision, scope=scope, reviewed_at=NOW
    )


def publication(reviews=None):
    return PublishedKnowledgeV1(
        revision=REVISION,
        published_by_student_id="student-a",
        published_at=NOW,
        classified_node_ids=("p1-subtopic",),
        taxonomy_version="taxonomy-2027.1",
        reviews=reviews or (review("student-a"),),
    )


def question():
    return CompleteQuestionV1(
        question_id="q1",
        content_revision="content-2",
        paper_id="s2023.P1",
        source_attempt_id="2024-05",
        display_label="Q1",
        common_stem="The company reported the following balances.",
        question_text="Use the balances to answer every part.",
        parts=(
            dict(id="q1-a", label="(a)", sequence=0, question_text="Compute revenue.",
                 source_spans=(SPAN,)),
            dict(id="q1-b", label="(b)", sequence=1, question_text="Explain the treatment.",
                 source_spans=(SPAN,)),
        ),
        answers=(
            dict(id="answer-a", question_part_id="q1-a", sequence=0,
                 answer_text="Revenue is 100, based on the calculation.", source_spans=(SPAN,)),
            dict(id="answer-b", question_part_id="q1-b", sequence=1,
                 answer_text="The applicable treatment follows the standard.", source_spans=(SPAN,)),
        ),
        answer_status="complete",
        source_spans=(SPAN,),
    )


def test_authenticated_published_content_can_represent_full_question_and_answers():
    response = PublishedContentResponseV1(
        authenticated_student=AuthenticatedStudentV1(
            student_id="student-b", authentication_subject="identity-b", invited=True
        ),
        publication=publication(),
        question=question(),
    )
    payload = response.model_dump(mode="json")
    assert payload["contract_version"] == "shared-study.v1"
    assert payload["question"]["common_stem"].startswith("The company")
    assert [part["label"] for part in payload["question"]["parts"]] == ["(a)", "(b)"]
    assert "Revenue is 100" in payload["question"]["answers"][0]["answer_text"]
    assert payload["publication"]["classification_verification_count"] == 1
    # Verification counts are read-only computed output fields.
    assert PublishedContentResponseV1.model_validate(
        response.model_dump(mode="json", round_trip=True)
    ).question == question()


def test_one_review_permits_publication_and_distinct_reviewers_are_counted_by_scope():
    assert publication().classification_verification_count == 1
    published = publication((
        review("student-a"), review("student-a"),
        review("student-b", VerificationScopeV1.CLASSIFICATION),
    ))
    assert published.classification_verification_count == 2
    assert published.content_verification_count == 1


@pytest.mark.parametrize("field", ["content_revision", "classification_revision"])
def test_verification_cannot_transfer_to_a_changed_revision(field):
    new_revision = REVISION.model_copy(update={field: "changed"})
    with pytest.raises(ValidationError, match="different published revision"):
        publication((review("student-a"), review("student-b", revision=new_revision)))


def test_publication_requires_identified_classification_reviewer():
    with pytest.raises(ValidationError, match="classification review"):
        publication((review("student-a", VerificationScopeV1.CONTENT),))


def test_published_response_rejects_unpublished_or_different_content():
    payload = dict(
        authenticated_student=AuthenticatedStudentV1(
            student_id="student-a", authentication_subject="identity-a", invited=True
        ),
        publication=publication(), question=question(),
    )
    with pytest.raises(ValidationError):
        PublishedContentResponseV1(**payload, visibility="staging")
    payload["question"] = question().model_copy(update={"content_revision": "unreviewed"})
    with pytest.raises(ValidationError, match="published revision"):
        PublishedContentResponseV1(**payload)


def test_private_response_has_explicit_authenticated_owner_and_default_target():
    student = AuthenticatedStudentV1(
        student_id="student-a", authentication_subject="identity-a", invited=True
    )
    record = PrivateStudyRecordV1(
        owner_student_id="student-a", node_id="p1-subtopic", progress="done",
        notes="Private note", updated_at=NOW,
    )
    assert PrivateStudyResponseV1(authenticated_student=student, record=record)
    assert record.target_attempt_id == "2027-05"
    with pytest.raises(ValidationError, match="different authenticated student"):
        PrivateStudyResponseV1(
            authenticated_student=student,
            record=record.model_copy(update={"owner_student_id": "student-b"}),
        )


def test_official_module_path_and_paper_specific_unit_root_are_representable():
    node = TaxonomyNodeV1(
        id="chapter-1", paper_id="s2023.P1", parent_id="module-1", level="chapter",
        name="Official chapter", sequence=0, stable_path=("module-1", "chapter-1"),
        taxonomy_version="taxonomy-2027.1", source_spans=(SPAN,),
        applicability_reference_ids=("guideline-2027-05",),
    )
    assert node.stable_path[0] == "module-1"
    unit = TaxonomyNodeV1(
        id="ibs-case-unit", paper_id="s2023.P6", parent_id=None, level="unit",
        name="Official unit", sequence=0, stable_path=("ibs-case-unit",),
        taxonomy_version="taxonomy-2027.1", source_spans=(SPAN,),
        applicability_reference_ids=("guideline-2027-05",),
        source_structure_note="This source has units without modules.",
    )
    assert unit.parent_id is None
    with pytest.raises(ValidationError, match="parent"):
        TaxonomyNodeV1(**(node.model_dump() | {"parent_id": "unrelated-module"}))


def test_score_separates_raw_marks_from_normalized_components_and_context():
    context = ScoreContextV1(
        target_attempt_id="2027-05", taxonomy_version="taxonomy-2027.1",
        material_applicability_version="applicability-2027.1", scoring_version="score-v2",
        published_corpus_revision="corpus-15",
    )
    score = ScoreSnapshotV1(
        score_run_id=1, node_id="p1-subtopic", context=context,
        exam=ScoreComponentV1(raw_value=7.5, raw_unit="decayed_marks", normalized_value=.75, weight=.6),
        practice=ScoreComponentV1(raw_value=2, raw_unit="decayed_marks", normalized_value=.2, weight=.2),
        weight_prior=ScoreComponentV1(raw_value=1.47, raw_unit="marks", normalized_value=.147, weight=.2),
        importance=.5194, computed_at=NOW, source_updated_at=NOW, freshness="fresh",
    )
    assert score.exam.raw_value == 7.5
    assert score.exam.normalized_value == .75
    assert score.context.target_attempt_id == "2027-05"
    with pytest.raises(ValidationError, match="sum to one"):
        ScoreSnapshotV1(**(score.model_dump() | {
            "exam": score.exam.model_copy(update={"weight": .9})
        }))


def test_question_part_order_and_answer_lineage_are_explicit():
    payload = question().model_dump()
    with pytest.raises(ValidationError, match="increasing sequence"):
        CompleteQuestionV1(**(payload | {"parts": tuple(reversed(payload["parts"]))}))
    payload["answers"][0]["question_part_id"] = "other-question"
    with pytest.raises(ValidationError, match="refer to a part"):
        CompleteQuestionV1(**payload)
