"""Deterministic extraction regression cases; live coverage is tracked separately."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import pytest

from caf_l2.blocks import LineBlock, OCRConfig, OCRUnavailableError, build_block_stream
from caf_l2.pairing import pair_answers, pair_cross_doc_answers
from caf_l2.profiles import ProfileNotFoundError, load_profile, resolve_profile
from caf_l2.segmenter import ParsedUnit, Segmenter, compute_fingerprint
from caf_l2.validators import DocumentValidator


def blocks(*texts: str) -> list[LineBlock]:
    return [LineBlock(f"p1-b{i}", 1, (0, i * 10, 200, i * 10 + 8), text, 10, False, "test", raw_text=text, order=i) for i, text in enumerate(texts)]


def profile(doc_type="suggested_answer"):
    return resolve_profile(Path("profiles"), "s2023", doc_type)


def parse(*texts, p=None):
    return Segmenter(p or profile(), "source-hash").segment(blocks(*texts))


def test_interleaved_answers_do_not_reset_for_nested_answer_parts():
    units = parse("Question 1", "Shared facts", "(a) Explain recognition", "(i) Initial recognition", "(ii) Subsequent measurement", "Answer", "(i) Initial answer", "(ii) Subsequent answer", "(b) Explain disclosure", "Answer", "Disclosure answer")
    a, b = units[0].children
    assert len(a.children) == 2
    assert a.children[0].answer_text == "(i) Initial answer"
    assert a.children[1].answer_text == "(ii) Subsequent answer"
    assert b.question_text == "(b) Explain disclosure"
    assert b.answer_text == "Disclosure answer"
    assert units[0].question_text == "Question 1\nShared facts"
    assert units[0].block_start == "p1-b0"


def test_sectioned_answers_merge_question_tree_and_retain_spans():
    p = replace(profile(), mode="sectioned")
    units = parse("Question 1", "(a) First question", "(b) Second question", "Question 2", "(a) Third question", "Answers", "Question 1", "(a) First answer", "(b) Second answer", "Question 2", "(a) Third answer", p=p)
    assert len(units) == 2
    assert units[0].children[0].answer_text == "(a) First answer"
    answers = pair_answers(units)
    assert answers["Q1.a"].block_start == "p1-b7"
    assert answers["Q1.a"].status == "matched"


def test_answer_only_stores_answer_not_question():
    units = parse("Question 1", "(a) Answer calculation", "Continued table row", p=profile("answer_only"))
    assert units[0].question_text == ""
    assert units[0].children[0].answer_text == "(a) Answer calculation\nContinued table row"
    result = DocumentValidator(profile("answer_only")).validate(units, pair_answers(units))
    assert not any(issue.code == "V5_UNIT_EMPTY" for issue in result.issues)


def test_cross_document_pairing_never_invents_answer_and_detects_duplicates():
    questions = parse("Question 1", "(a) Question text", p=profile("question_paper"))
    unparsed_answers = parse("Question 1", "(a) This is question text", p=profile("question_paper"))
    paired = pair_cross_doc_answers(questions, unparsed_answers, 42)
    assert paired["Q1.a"].answer_text is None
    assert paired["Q1.a"].answer_doc_id == 42
    answers = parse("Question 1", "(a) Answer text", p=profile("answer_only"))
    paired = pair_cross_doc_answers(questions, answers + answers, 42)
    assert paired["Q1.a"].status == "ambiguous"
    assert paired["Q1.a"].answer_text is None
    assert len(paired["Q1.a"].candidates) == 2
    assert paired["Q1.a"].candidates[0]["answer_doc_id"] == 42
    assert paired["Q1.a"].candidates[0]["answer_text"] == "(a) Answer text"


def test_or_alternatives_scoped_and_marks_counted_once():
    units = parse("Question 1", "Shared facts (10 Marks)", "(a) First question (10 Marks)", "OR", "(a) Alternative question (10 Marks)")
    assert [c.label_path for c in units[0].children] == ["Q1.a", "Q1.a.alt2"]
    assert units[0].children[0].or_group == units[0].children[1].or_group
    assert units[0].marks == 10
    p = replace(profile(), paper_max=10, expects_answers=False)
    result = DocumentValidator(p).validate(units, {})
    assert not any(i.code.startswith("V3_") for i in result.issues)


def test_full_content_fingerprint_changes_after_200_characters():
    first = "a" * 300 + "First amount: 100"
    second = "a" * 300 + "Second amount: 200"
    assert compute_fingerprint("hash", "Q1.a", first) != compute_fingerprint("hash", "Q1.a", second)
    assert len(compute_fingerprint("hash", "Q1.a", first)) == 40


def test_question_only_does_not_require_answers_or_mcq_keys():
    p = profile("question_paper")
    result = DocumentValidator(p).validate(parse("Question 1", "A complete question (100 Marks)", p=p), {})
    assert not any(i.code.startswith("V4_") for i in result.issues)


def test_practice_collection_has_no_fixed_total():
    p = profile("rtp")
    result = DocumentValidator(p).validate(parse("Question 1", "A complete question", "Answer", "A complete answer", p=p), {})
    assert p.paper_max is None
    assert not any(i.code.startswith("V3_") or i.code == "V2_MISSING_MARKS" for i in result.issues)


def test_profile_requires_explicit_role(tmp_path):
    path = tmp_path / "unsupported.yaml"
    path.write_text("id: unknown\napplies_to:\n  scheme: s2023\n  doc_type: unknown\nmode: interleaved\n")
    with pytest.raises(ProfileNotFoundError, match="unsupported_profile"):
        load_profile(path)


def test_native_blocks_retain_raw_text_origin_and_order():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Question 1")
    page.insert_text((72, 92), "Amount  100")
    extracted = build_block_stream(doc)
    assert extracted[1].raw_text == "Amount  100"
    assert extracted[1].text == "Amount 100"
    assert extracted[1].origin == "pdf"
    assert extracted[0].order < extracted[1].order
    doc.close()


def test_scanned_page_has_explicit_ocr_unavailable_state():
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), 0)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    with pytest.raises(OCRUnavailableError, match="ocr_unavailable.*page 1"):
        build_block_stream(doc)
    with patch("caf_l2.blocks.shutil.which", return_value=None):
        with pytest.raises(OCRUnavailableError, match="Tesseract is missing"):
            build_block_stream(doc, ocr_config=OCRConfig())
    doc.close()


@pytest.mark.parametrize("name", ["rtp_p1_nov2026_case1", "rtp_p1_nov2026_question11", "ibs_digest_volume2_case1", "model_p1_collection2025_question1", "model_p1_collection2025_answer1", "model_p1_collection2025_case1_mixed", "exam_p3_may2026_integrated_case1_ocr", "ibs_practice_sep2026_facts_only"])
def test_authentic_source_backed_expected_tree(name):
    import hashlib
    import json

    fixture = json.loads((Path("profiles/fixtures") / f"{name}.json").read_text())
    lines = [LineBlock(**{**block, "bbox": tuple(block["bbox"]), "fidelity_flags": tuple(block["fidelity_flags"])}) for block in fixture["blocks"]]
    p = load_profile(Path(fixture["profile_path"])) if fixture.get("profile_path") else resolve_profile(Path("profiles"), "s2023", fixture["doc_type"], fixture["paper"])
    units = Segmenter(p, fixture["source_sha256"]).segment(lines)
    answers = pair_answers(units, key_patterns=p.patterns)

    def expected(unit):
        return {"label_path": unit.label_path, "question_text_sha256": hashlib.sha256(unit.question_text.encode()).hexdigest(), "answer_text_sha256": hashlib.sha256(unit.answer_text.encode()).hexdigest(), "mcq_options": len(unit.mcq_options), "mcq_key": answers[unit.label_path].mcq_correct_option if unit.label_path in answers else None, "children": [expected(child) for child in unit.children]}

    assert [expected(unit) for unit in units] == fixture["expected_tree"]
    source = Path(fixture["source_file"])
    if source.exists():
        assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["source_sha256"]
    assert all(fixture["source_pages"][0] <= line.page <= fixture["source_pages"][1] for line in lines)
    if name == "rtp_p1_nov2026_case1":
        assert [child.label_path for child in units[0].children] == [f"CS1.M{i}" for i in range(1, 6)]
        assert "KK Ltd." in units[0].question_text
        assert len(units[0].children[0].mcq_options) == 4
    if name == "rtp_p1_nov2026_question11":
        assert [child.label_path for child in units[0].children] == ["Q11.a", "Q11.b", "Q11.c", "Q11.d"]
        assert all(child.question_text and child.answer_text for child in units[0].children)
        assert "Right of return" in units[0].children[0].answer_text
        assert "30 crore" in units[0].question_text
    if name == "ibs_digest_volume2_case1":
        assert [child.label_path for child in units[0].children] == [f"CS1.M{i}" for i in range(1, 10)] + [f"CS1.Q{i}" for i in range(10, 14)]
        assert answers["CS1.M1"].mcq_correct_option == "C"
        assert "15th June 2025" in units[0].children[0].answer_text
        assert "Gordon Growth Model" in units[0].children[11].answer_text
    if name == "model_p1_collection2025_case1_mixed":
        assert [child.label_path for child in units[0].children] == [f"P1.T1.CS1.M{i}" for i in range(1, 7)]
        assert [answers[child.label_path].mcq_correct_option for child in units[0].children] == ["B", "C", "D", "A", "C", "D"]
        assert answers["P1.T1.CS1.M1"].page_start == 333
        assert "38%" in answers["P1.T1.CS1.M1"].answer_text
    if name == "exam_p3_may2026_integrated_case1_ocr":
        assert [child.label_path for child in units[0].children] == [f"CSI.M{i}" for i in range(1, 6)]
        assert units[0].marks == 10
        assert all(line.origin == "ocr" for line in lines)
        assert "Myra Developers" in units[0].question_text
        assert any("OCR_REVIEW_REQUIRED" in line.fidelity_flags for line in lines)
    if name == 'ibs_practice_sep2026_facts_only':
        assert len(units)==1 and units[0].children==[] and not units[0].is_gradable
        assert 'Soft Tech Limited' in units[0].question_text
        assert 'three-months credit' in units[0].question_text
    if name == "model_p1_collection2025_question1":
        assert "Flywing Airways Ltd" in units[0].question_text
        assert units[0].marks == 14
    if name == "model_p1_collection2025_answer1":
        assert "13,260" in units[0].answer_text
        assert "11,566" in units[0].answer_text
        assert units[0].question_text == ""


def test_split_mcq_key_rows_and_conflicting_keys():
    p = resolve_profile(Path("profiles"), "s2023", "rtp", "s2023.P1")
    from caf_l2.pairing import extract_mcq_key_table
    rows = ["Answer to Multiple Choice Questions", "1.", "(A)", "2.", "(C)", "1.", "(B)"]
    assert extract_mcq_key_table(rows, p.patterns) == {"2": "C"}


def test_declared_noncontent_page_exclusion_preserves_page_identity():
    doc = fitz.open()
    cover = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), 0)
    pix.clear_with(255)
    cover.insert_image(cover.rect, pixmap=pix)
    page = doc.new_page()
    page.insert_text((72, 72), "Question 1")
    extracted = build_block_stream(doc, ignored_pages={1})
    assert extracted[0].page == 2
    assert extracted[0].block_id.startswith("p2-")
    doc.close()


def test_mcq_options_preserve_multiline_content():
    units = parse("Case Scenario 1", "Shared scenario", "1. Select an answer", "(A) First option", "First option continues", "(B) Second option", "Second option continues", "(C) Third option", "(D) Fourth option")
    mcq = units[0].children[0]
    assert mcq.mcq_options == ["(A) First option\nFirst option continues", "(B) Second option\nSecond option continues", "(C) Third option", "(D) Fourth option"]


def test_ocr_cache_is_bound_to_source_and_config(tmp_path):
    from caf_l2.blocks import _page_dictionary

    class OCRPage:
        number = 0
        calls = 0

        def get_images(self):
            return ["scanned image"]

        def get_text(self, mode, **kwargs):
            if mode == "text":
                return ""
            if "textpage" in kwargs:
                return {"blocks": [{"type": 0, "lines": [{"bbox": [0, 0, 20, 10], "spans": [{"text": "Question 1"}]}]}]}
            return {"blocks": []}

        def get_textpage_ocr(self, **kwargs):
            self.calls += 1
            return "OCR textpage"

    page = OCRPage()
    with patch("caf_l2.blocks.shutil.which", return_value="/usr/bin/tesseract"):
        result, origin = _page_dictionary(page, OCRConfig(), "source-one", tmp_path)
        cached, cached_origin = _page_dictionary(page, OCRConfig(), "source-one", tmp_path)
        assert cached == result
        assert origin == cached_origin == "ocr"
        assert page.calls == 1
        _page_dictionary(page, OCRConfig(dpi=200), "source-one", tmp_path)
        _page_dictionary(page, OCRConfig(), "source-two", tmp_path)
        assert page.calls == 3


def test_repeated_answer_only_labels_are_ambiguous_with_source_evidence():
    questions = parse("Question 1", "(a) Actual question", p=profile("question_paper"))
    answers = parse("Question 1", "(a) First candidate", "Question 1", "(a) Second candidate", p=profile("answer_only"))
    paired = pair_cross_doc_answers(questions, answers, 17)
    assert paired["Q1.a"].status == "ambiguous"
    assert [candidate["answer_text"] for candidate in paired["Q1.a"].candidates] == ["(a) First candidate", "(a) Second candidate"]
    assert paired["Q1.a"].candidates[1]["block_start"] == "p1-b3"


def test_model_collection_numbers_are_scoped_by_test_and_paper():
    p = load_profile(Path("profiles/s2023.model_collection.P1.yaml"))
    lines = blocks("MODEL TEST PAPER 1", "PAPER 1: FINANCIAL REPORTING", "Case Scenario 1", "Shared first scenario", "appropriate option in the below questions 1 to 6", "1. First question", "(A) A", "(B) B", "(C) C", "(D) D", "MODEL TEST PAPER 2", "PAPER 1: FINANCIAL REPORTING", "Case Scenario 1", "Shared second scenario", "appropriate option in the below questions 1 to 6", "1. Second question", "(A) A", "(B) B", "(C) C", "(D) D", "ANSWERS OF MODEL TEST PAPER 1", "PAPER 1: FINANCIAL REPORTING", "PART – I CASE SCENARIO BASED MCQS", "1.", "Option (b): first answer", "ANSWERS OF MODEL TEST PAPER 2", "PAPER 1: FINANCIAL REPORTING", "PART – I CASE SCENARIO BASED MCQS", "1.", "Option (c): second answer")
    for line in lines:
        line.bold = True
    units = Segmenter(p, "collection-source").segment(lines)
    answers = pair_answers(units, key_patterns=p.patterns)
    assert len(units) == 2
    assert answers["P1.T1.CS1.M1"].mcq_correct_option == "B"
    assert answers["P1.T2.CS1.M1"].mcq_correct_option == "C"
    assert "first answer" in answers["P1.T1.CS1.M1"].answer_text
    assert "second answer" in answers["P1.T2.CS1.M1"].answer_text


def test_choice_instructions_from_remaining_questions_are_parsed():
    segmenter = Segmenter(profile(), "choice-source")
    units = segmenter.segment(blocks("Question No.1 is compulsory. Attempt any four questions from the remaining five questions.", "Question 1", "First complete question (20 Marks)", "Question 2", "Second complete question (20 Marks)"))
    assert segmenter.optional_pick == 4
    assert units[0].choice_role == "compulsory"
    assert units[1].choice_role == "optional"


def test_source_specific_ocr_profile_rejects_unreviewed_layout():
    p = resolve_profile(Path("profiles"), "s2023", "question_paper", "s2023.P3")
    with pytest.raises(ProfileNotFoundError, match="unsupported_profile"):
        Segmenter(p, "unreviewed-source").segment(blocks("Question 1", "Unreviewed layout"))


def test_fidelity_flags_are_deduplicated_per_unit_page():
    p = profile("question_paper")
    lines = blocks("Question 1", "First text", "Second text", "Third text")
    for line in lines:
        line.fidelity_flags = ("OCR_REVIEW_REQUIRED",)
    units = Segmenter(p, "source").segment(lines)
    result = DocumentValidator(p).validate(units, {})
    assert sum(issue.code == "OCR_REVIEW_REQUIRED" for issue in result.issues) == 1
