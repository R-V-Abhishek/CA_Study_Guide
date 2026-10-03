import json
from pathlib import Path

import pymupdf
import pytest

from caf_l0.sources import TextbookSection, pdf_evidence, question_route, select_sections


def section(key, attempts, verified=True):
    return TextbookSection(key, "edition-evidence", tuple(attempts), "https://resource.cdn.icai.org/file.pdf", verified)


def test_partial_target_preserves_expected_sections_and_only_january_fallback():
    result = select_sections(["1", "2", "3", "4"], [
        section("1", ["2027-05"]), section("1", ["2026-01"]),
        section("2", ["2026-01"]), section("3", ["2026-11"]),
        section("4", ["2027-05"], verified=False),
    ])
    assert len(result) == 4
    assert result[0].section.applicable_attempts == ("2027-05",)
    assert not result[0].fallback
    assert result[1].fallback
    assert result[2].section is None and result[2].gap
    assert result[3].section is None


def test_ambiguous_source_selection_requires_evidence_review():
    with pytest.raises(ValueError, match="Ambiguous"):
        select_sections(["1"], [section("1", ["2027-05"]), section("1", ["2027-05"])])


@pytest.mark.parametrize("level,route", [("Final", "final_queue"), ("Intermediate", "outside_corpus"), ("Foundation", "outside_corpus")])
def test_model_source_attempt_nullable_and_course_routing(level, route):
    assert question_route(level, "model_question", None) == route
    assert question_route(level, "mtp_question", "2026-01") == route
    with pytest.raises(ValueError, match="source attempt"):
        question_route(level, "mtp_question", None)


def test_pdf_heading_evidence_excludes_answer_and_exercise_sections(tmp_path):
    path = tmp_path / "textbook.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 45), "2.1 DIRECT TAX LAWS", fontsize=16)
        page.insert_text((50, 100), "1. RISK MANAGEMENT", fontsize=16)
        page.insert_text((50, 200), "2. TEST YOUR KNOWLEDGE", fontsize=16)
        page.insert_text((50, 300), "3. ANSWERS", fontsize=16)
        document.save(path)
    digest, pages, headings = pdf_evidence(path)
    assert len(digest) == 64 and pages == 1
    assert [(h.number, h.title, h.pdf_page) for h in headings] == [("1", "RISK MANAGEMENT", 1)]


def test_wrapped_display_heading_is_joined_without_its_body_paragraph(tmp_path):
    path = tmp_path / "wrapped.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "2. INTRODUCTION OF", fontsize=16)
        page.insert_text((50, 120), "IND AS IN INDIA", fontsize=16)
        page.insert_text((50, 155), "The accounting standards apply to entities.", fontsize=11)
        page.insert_text((50, 205), "3.3 Example:", fontsize=14)
        document.save(path)
    _, _, headings = pdf_evidence(path)
    assert [(h.number, h.title) for h in headings] == [("2", "INTRODUCTION OF IND AS IN INDIA")]


def test_lettered_cost_sections_preserve_small_bold_subheadings_and_context(tmp_path):
    path = tmp_path / "cost.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "A. MANAGING COST STRATEGICALLY", fontsize=14, fontname="hebo")
        page.insert_text((50, 140), "1. Traditional Cost Management", fontsize=12, fontname="hebo")
        page.insert_text((50, 180), "2.1 Value Chain Analysis", fontsize=11, fontname="hebo")
        page.insert_text((50, 240), "TEST YOUR KNOWLEDGE", fontsize=14, fontname="hebo")
        page.insert_text((50, 280), "3. A practice prompt", fontsize=12, fontname="hebo")
        document.save(path)
    _, _, headings = pdf_evidence(path, min_heading_size=11, allow_lettered=True)
    assert [h.number for h in headings] == ["A", "1", "2.1"]
    assert all(h.section_context == "MANAGING COST STRATEGICALLY" for h in headings)


def test_separate_instruments_reset_exercises_and_keep_repeated_definition_headings(tmp_path):
    path = tmp_path / "sebi.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "SEBI (LODR) REGULATIONS, 2015", fontsize=15.96, fontname="hebo")
        page.insert_text((50, 150), "1. DEFINITIONS", fontsize=15.96, fontname="hebo")
        page.insert_text((50, 240), "TEST YOUR KNOWLEDGE", fontsize=15.96, fontname="hebo")
        page.insert_text((50, 320), "SEBI (PIT) REGULATIONS, 2015", fontsize=15.96, fontname="hebo")
        page.insert_text((50, 370), "1. DEFINITIONS", fontsize=15.96, fontname="hebo")
        document.save(path)
    _, _, headings = pdf_evidence(path)
    assert len(headings) == 2
    assert headings[0].instrument_context == "SEBI (LODR) REGULATIONS, 2015"
    assert headings[1].instrument_context == "SEBI (PIT) REGULATIONS, 2015"


def test_question_inventory_explicit_types_and_actual_level_routing():
    source = json.loads((Path(__file__).parents[1] / "taxonomy/textbook_v1/question_sources.json").read_text())
    for record in source["records"]:
        if record["artifact_role"] == "announcement":
            assert record["doc_type_id"] is None
            assert record["classification_queue"] == "not_question_artifact"
        elif record["course_level"] != "Final":
            assert record["classification_queue"] == "outside_corpus"
        if record["source_family"] == "model" and record["artifact_role"] != "announcement":
            assert record["doc_type_id"] in {"model_question", "model_answer"}
            assert record["attempt_id"] is None


def test_committed_source_matrix_is_independent_and_unapproved():
    path = Path(__file__).parents[1] / "taxonomy/textbook_v1/manifest.json"
    manifest = json.loads(path.read_text())
    assert {p["paper_id"] for p in manifest["papers"]} == {f"s2023.P{i}" for i in range(1, 7)}
    assert manifest["target_attempt"] == "2027-05"
    assert manifest["release_approval"] is None
    assert all(d["review_status"] == "pending" for d in manifest["descriptors"])
    assert all(a["applicable_attempts"] == ["2026-01"] or "2027-05" in a["applicable_attempts"] for a in manifest["textbook_artifacts"])
    identities = json.loads((path.parent / "identities.json").read_text())
    assert set(n["id"] for n in manifest["nodes"]) <= set(identities.values())
