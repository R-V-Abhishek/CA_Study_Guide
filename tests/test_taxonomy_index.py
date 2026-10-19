"""Contents extraction remains deterministic and review-only."""

from pathlib import Path

import pymupdf

from caf_l0.index_parser import build_index_report, extract_index, parse_index_pages


def test_wrapped_index_preserves_hierarchy_and_evidence():
    entries, unresolved = parse_index_pages([
        (15, "DETAILED CONTENTS: MODULE – 1\nCHAPTER 1: INTRODUCTION\nTO ACCOUNTING\n1.\nIntroduction ........ 1.3\n1.1\nFirst part of a"),
        (16, "xvi\nwrapped heading ....... 1.4\nTest Your Knowledge ..... 1.5\n© The Institute of Chartered Accountants of India"),
    ])
    assert not unresolved
    assert [entry.kind for entry in entries] == ["module", "chapter", "topic", "subtopic"]
    assert entries[1].title == "INTRODUCTION TO ACCOUNTING"
    assert entries[3].title == "First part of a wrapped heading"
    assert entries[3].parent_id == entries[2].id
    assert entries[3].source_pdf_pages == [15, 16]
    assert entries[3].printed_page_reference == "1.4"


def test_missing_prefix_is_flagged_instead_of_invented():
    entries, unresolved = parse_index_pages([(1, "CHAPTER 1: Basics\n3.2 Detail .... 1.9\nUnknown heading")])
    assert len(entries) == 2
    assert entries[1].parent_id == entries[0].id
    assert [item["reason"] for item in unresolved] == ["number_prefix_not_observed", "unparsed_line"]


def test_chapter_and_unit_numbers_are_observed_prefixes():
    entries, unresolved = parse_index_pages([(1, "CHAPTER 2: Framework\n2.1 First topic .... 2.1\nUnit 3: Reporting\n3.1 Another topic .... 2.3\n3.1.1 Detail .... 2.4")])
    assert not unresolved
    assert [entry.kind for entry in entries] == ["chapter", "topic", "unit", "topic", "subtopic"]
    assert entries[1].parent_id == entries[0].id
    assert entries[3].parent_id == entries[2].id
    assert entries[4].parent_id == entries[3].id


def test_pdf_auto_selection_starts_at_detailed_contents(tmp_path: Path):
    path = tmp_path / "front.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 40), "SYLLABUS\n1. Not an index entry .... 1.1")
        pdf.new_page().insert_text((40, 40), "DETAILED CONTENTS: MODULE 1\nCHAPTER 1: Basics\n1. Useful topic .... 1.3")
        pdf.save(path)
    result = extract_index(path)
    assert result["selected_pdf_pages"] == [2]
    assert len(result["entries"]) == 3
    assert result["entries"][-1]["source_pdf_pages"] == [2]


def test_report_missing_source_is_visible_and_never_published(tmp_path: Path):
    manifest = {"version_id": "draft", "target_attempt": "2027-05", "nodes": [], "textbook_artifacts": [
        {"id": "a", "paper_id": "P1", "artifact_role": "front_matter", "local_path": "missing.pdf", "download_url": "https://example.test/missing"},
    ]}
    report = build_index_report(manifest, tmp_path)
    assert report["published"] is False
    assert report["status"] == "draft_requires_curator_review"
    assert report["sources"][0]["source_issue"] == "Local front-matter PDF is missing"
