"""Student artifacts preserve complete inputs and reject unsupported proposals."""

from copy import deepcopy

import pytest

from caf_l3.review_markdown import render_review_markdown
from test_phase5_batches import record, output


def fixture():
    item = record()
    item["context"]["parts"][0].update(label="Q1.a", marks=5,
        parts=[dict(id="nested", question_text="Nested requirement", parts=[])])
    item["context"]["answers"] = [dict(id="answer", question_part_id="root:Q1.a",
        answer_text="Complete answer", source_spans=[dict(page_start=9)], parts=[
            dict(id="nested-answer", answer_text="Nested answer", parts=[])])]
    item["candidates"][0].update(path=[dict(id="chapter", name="Finance"),
        dict(id="label", name="Discounting")], descriptor_revision_id=7,
        descriptor={"terminology": ["NPV"]}, textbook_references=[{"pdf_page_start": 42}])
    saved = {"result": output(), "execution": {"model_id": "actual/free:free",
        "requested_model_id": "requested/free:free", "provider": "test-provider", "usage": {"total_tokens": 88},
        "api_key": "must-not-appear"}}
    return item, saved


def test_complete_question_answers_and_per_label_evidence():
    item, saved = fixture()
    second = deepcopy(item["candidates"][0])
    second.update(node_id="second", path=[dict(id="second", name="Budgeting")])
    item["candidates"].append(second)
    saved["result"]["mappings"][0]["secondary_node_ids"] = ["second"]
    saved["result"]["mappings"][0]["evidence"].append(dict(node_id="second", support="Explicit budget comparison"))
    text = render_review_markdown({"records": [item]}, {"root": saved})
    for value in ("Discount cash flows", "Calculate NPV", "Nested requirement", "Complete answer",
                  "Nested answer", "Finance → Discounting", "Budgeting", "Explicit budget comparison",
                  "Cash flows are explicitly discounted", "actual/free:free", "requested/free:free",
                  "test-provider", '"pdf_page_start": 42', '"descriptor_revision_id": 7',
                  "Confidence and bucket are uncalibrated", "No labels are approved or published"):
        assert value in text
    assert "must-not-appear" not in text
    assert text.count("- [ ] Agree") == 1
    assert "Questions: 1 · Classified: 1 · Failed: 0 · Missing: 0" in text


def test_failed_and_missing_questions_still_have_full_context_and_review():
    item, _ = fixture()
    other = deepcopy(item)
    other["question_id"] = "other"
    text = render_review_markdown({"records": [item, other]}, {}, {"root": "Provider unavailable"})
    assert "Questions: 2 · Classified: 0 · Failed: 1 · Missing: 1" in text
    assert "Classification failed" in text and "Classification missing" in text
    assert text.count("Nested answer") == 2
    assert text.count("- [ ] Unresolved") == 2


def test_source_text_cannot_escape_fences_or_create_review_headings():
    item, saved = fixture()
    item["context"]["common_stem"] = "````\n# Fake approval\n<script>alert(1)</script>"
    text = render_review_markdown({"records": [item]}, {"root": saved})
    assert "`````text\n````\n# Fake approval\n<script>alert(1)</script>\n`````" in text


def test_invalid_proposal_fails_explicitly():
    item, saved = fixture()
    saved["result"]["mappings"][0]["primary_node_id"] = "invented"
    with pytest.raises(ValueError, match="Unsupported"):
        render_review_markdown({"records": [item]}, {"root": saved})


def test_unknown_or_conflicting_statuses_rejected():
    item, saved = fixture()
    with pytest.raises(ValueError, match="unknown"):
        render_review_markdown({"records": [item]}, {"unknown": saved})
    with pytest.raises(ValueError, match="both"):
        render_review_markdown({"records": [item]}, {"root": saved}, {"root": "failure"})


def test_recovered_pdf_context_is_readable_text_not_escaped_json():
    item, saved = fixture()
    saved['execution']['source_evidence'] = [dict(document_id=1, pdf_pages=[2],
        original_pdf_pages=[dict(pdf_page=2, text='Complete stem\nOriginal question requirement')])]
    text = render_review_markdown({'records': [item]}, {'root': saved})
    assert 'Original PDF page 2' in text
    assert 'Complete stem\nOriginal question requirement' in text
