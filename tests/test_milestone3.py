"""Milestone 3 L2 Extraction Test Suite."""

from pathlib import Path
import pymupdf as fitz
import pytest

from caf_common.blob_store import BlobStore
from caf_common.run_context import open_run
from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.ingest import Document, Unit, UnitAnswer
from caf_l2.blocks import LineBlock, build_block_stream, normalize_text
from caf_l2.overrides import apply_override
from caf_l2.pairing import pair_answers
from caf_l2.pipeline import ExtractionPipeline
from caf_l2.preflight import preflight_check
from caf_l2.profiles import ProfileNotFoundError, resolve_profile
from caf_l2.render import render_debug_html
from caf_l2.segmenter import ParsedUnit, Segmenter
from caf_l2.validators import DocumentValidator


def test_preflight_and_blocks(tmp_path: Path):
    # 1. Create a 3-page test PDF with headers, footers, and text
    doc_path = tmp_path / "sample_preflight.pdf"
    doc = fitz.open()

    for p in range(1, 4):
        page = doc.new_page(width=595, height=842)
        # Repeating header in top 8% (y <= 67)
        page.insert_text((50, 40), "THE INSTITUTE OF CHARTERED ACCOUNTANTS OF INDIA", fontsize=9)
        # Repeating footer in bottom 8% (y >= 774)
        page.insert_text((50, 800), "© The Institute of Chartered Accountants of India", fontsize=9)
        # Standalone page number
        page.insert_text((500, 800), f"Page {p}", fontsize=9)
        # Main content (> 200 characters to test text layer threshold)
        page.insert_text(
            (50, 150),
            f"This is page {p} content with rupee sign \u20b9 5,00,000 and ligature ﬁnancial reporting. "
            "The Chartered Accountant curriculum demands thorough and systematic preparation across "
            "all core subjects including financial reporting, auditing, taxation, and business laws.",
            fontsize=11,
        )

    doc.save(str(doc_path))
    doc.close()

    # Verify preflight
    opened_doc = fitz.open(str(doc_path))
    pf = preflight_check(opened_doc)
    assert pf.page_count == 3
    assert pf.has_text_layer is True

    # Verify block stream cleaning
    blocks = build_block_stream(opened_doc)
    opened_doc.close()

    block_texts = [b.text for b in blocks]
    # Header and footer must be stripped
    assert not any("INSTITUTE OF CHARTERED" in t for t in block_texts)
    assert not any("© The Institute" in t for t in block_texts)
    assert not any(t == f"Page {p}" for p in range(1, 4) for t in block_texts)

    # Verify normalize_text handles ligatures and rupee sign
    assert normalize_text("Rupee \uf0b9 5,00,000 and ligature \ufb01nancial") == "Rupee ₹ 5,00,000 and ligature financial"
    assert any("5,00,000" in t and "Chartered Accountant" in t for t in block_texts)


def test_profile_resolution():
    profiles_dir = Path("profiles")
    profile = resolve_profile(
        profiles_dir=profiles_dir,
        scheme_id="s2023",
        doc_type_id="suggested_answer",
        paper_id="s2023.P1",
    )
    assert profile.id == "s2023.suggested_answer.v1"
    assert profile.paper_max == 100
    assert profile.mode == "interleaved"

    with pytest.raises(ProfileNotFoundError):
        resolve_profile(
            profiles_dir=profiles_dir,
            scheme_id="unknown_scheme",
            doc_type_id="unknown_doc_type",
        )


def _build_synthetic_suggested_answer_pdf(pdf_path: Path) -> None:
    """Helper to create a 100-mark synthetic Suggested Answer PDF."""
    doc = fitz.open()

    # Page 1: Instructions & Question 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(
        (50, 50),
        "INSTRUCTIONS: Question No. 1 is compulsory. Attempt any four questions from the remaining five questions.\n",
        fontsize=10,
    )
    p1.insert_text((50, 100), "Question 1\n", fontsize=14)
    p1.insert_text((50, 130), "(a) Explain the recognition criteria under Ind AS 115 with reference to contract modifications.\n(10 Marks)\n", fontsize=11)
    p1.insert_text((50, 200), "Answer\nUnder Ind AS 115, a contract modification is accounted for as a separate contract if...\n", fontsize=11)
    p1.insert_text((50, 300), "(b) XYZ Ltd faces a legal claim. Assess whether provision is required under Ind AS 37.\n(10 Marks)\n", fontsize=11)
    p1.insert_text((50, 370), "Answer\nAs per Ind AS 37, a provision should be recognized when there is a present obligation...\n", fontsize=11)

    # Page 2: Question 2 & Question 3
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "Question 2\n", fontsize=14)
    p2.insert_text((50, 80), "(a) Prepare the Consolidated Balance Sheet of Parent Ltd and Subsidiary Ltd under Ind AS 110.\n(14 Marks)\n", fontsize=11)
    p2.insert_text((50, 150), "Answer\nConsolidated Balance Sheet as at 31st March 2024 reflects goodwill of Rs 40 lakhs...\n", fontsize=11)
    p2.insert_text((50, 250), "(b) Discuss the professional ethics requirements under CA Act 1949.\n(6 Marks)\n", fontsize=11)
    p2.insert_text((50, 320), "Answer\nUnder Clause 1 of Part II of Second Schedule, a member is guilty if...\n", fontsize=11)

    p2.insert_text((50, 420), "Question 3\n", fontsize=14)
    p2.insert_text((50, 450), "(a) Calculate purchase consideration in a business combination under Ind AS 103.\n(12 Marks)\n", fontsize=11)
    p2.insert_text((50, 520), "Answer\nPurchase consideration includes fair value of equity instruments issued...\n", fontsize=11)
    p2.insert_text((50, 600), "(b) Value the employee stock options using Black-Scholes formula under Ind AS 102.\n(8 Marks)\n", fontsize=11)
    p2.insert_text((50, 670), "Answer\nFair value per option is calculated as...\n", fontsize=11)

    # Page 3: Questions 4, 5, 6
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 50), "Question 4\n", fontsize=14)
    p3.insert_text((50, 80), "(a) Determine lease liability and ROU asset under Ind AS 116.\n(10 Marks)\n", fontsize=11)
    p3.insert_text((50, 140), "Answer\nLease liability is present value of lease payments discounted at incremental borrowing rate...\n", fontsize=11)
    p3.insert_text((50, 220), "(b) Classify financial asset into FVTPL vs FVTOCI under Ind AS 109.\n(10 Marks)\n", fontsize=11)
    p3.insert_text((50, 280), "Answer\nBusiness model test and SPPI test determine classification...\n", fontsize=11)

    p3.insert_text((50, 360), "Question 5\n", fontsize=14)
    p3.insert_text((50, 390), "(a) Discuss level 1, 2, and 3 inputs for fair value measurement under Ind AS 113.\n(10 Marks)\n", fontsize=11)
    p3.insert_text((50, 450), "Answer\nLevel 1 inputs are quoted prices in active markets for identical assets...\n", fontsize=11)
    p3.insert_text((50, 520), "(b) Identify reportable operating segments based on 10 percent quantitative thresholds.\n(10 Marks)\n", fontsize=11)
    p3.insert_text((50, 580), "Answer\nSegments meeting revenue, profit or asset threshold of 10 percent are reportable...\n", fontsize=11)

    # Page 4: Question 6
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text((50, 50), "Question 6\n", fontsize=14)
    p4.insert_text((50, 80), "(a) Explain functional currency determination under Ind AS 21.\n(12 Marks)\n", fontsize=11)
    p4.insert_text((50, 140), "Answer\nPrimary factors include the currency that mainly influences sales prices...\n", fontsize=11)
    p4.insert_text((50, 240), "(b) Disclose related party relationships and transactions under Ind AS 24.\n(8 Marks)\n", fontsize=11)
    p4.insert_text((50, 300), "Answer\nControl and significant influence relationships must be disclosed irrespective of transactions...\n", fontsize=11)

    doc.save(str(pdf_path))
    doc.close()


def test_segmentation_pairing_and_validation(tmp_path: Path):
    pdf_path = tmp_path / "synthetic_sa.pdf"
    _build_synthetic_suggested_answer_pdf(pdf_path)

    doc = fitz.open(str(pdf_path))
    lines = build_block_stream(doc)
    doc.close()

    profile = resolve_profile(Path("profiles"), "s2023", "suggested_answer")
    segmenter = Segmenter(profile=profile, doc_sha256="test_sha_123")
    units = segmenter.segment(lines)

    # 1. Structure check: 6 questions
    assert len(units) == 6
    assert [u.label_path for u in units] == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]

    # 2. Compulsory detection: Q1 compulsory, Q2-Q6 optional
    assert units[0].choice_role == "compulsory"
    assert all(u.choice_role == "optional" for u in units[1:])

    # 3. Parts and marks check
    q1 = units[0]
    assert len(q1.children) == 2
    assert q1.children[0].label_path == "Q1.a"
    assert q1.children[0].marks == 10
    assert q1.children[1].label_path == "Q1.b"
    assert q1.children[1].marks == 10
    assert q1.marks == 20
    assert q1.marks_source == "summed"
    assert q1.is_gradable is False
    assert q1.children[0].is_gradable is True

    # 4. Answers pairing
    answers = pair_answers(units, mode=profile.mode)
    assert "Q1.a" in answers
    assert answers["Q1.a"].answer_text is not None
    assert "Ind AS 115" in answers["Q1.a"].answer_text
    assert answers["Q1.a"].pairing_method == "same_doc"

    # 5. Validation check: attemptable marks is 20 + (4 * 20) = 100
    validator = DocumentValidator(profile=profile, has_answers=True, optional_pick=segmenter.optional_pick)
    val_res = validator.validate(units, answers)
    assert not val_res.has_errors
    assert val_res.outcome in ("ok", "ok_with_warnings")


def test_validator_detects_deliberate_errors():
    profile = resolve_profile(Path("profiles"), "s2023", "suggested_answer")

    # Deliberate V1 error: Q1, Q3 (Q2 missing)
    u1 = ParsedUnit(
        label_path="Q1", display_label="Question 1", kind="question",
        page_start=1, page_end=1, block_start="p1-b1", block_end="p1-b5",
        marks=20, is_gradable=True, choice_role="compulsory",
    )
    u3 = ParsedUnit(
        label_path="Q3", display_label="Question 3", kind="question",
        page_start=2, page_end=2, block_start="p2-b1", block_end="p2-b5",
        marks=20, is_gradable=True, choice_role="optional",
    )
    ans = pair_answers([u1, u3], mode="interleaved")
    validator = DocumentValidator(profile=profile, has_answers=True)
    res = validator.validate([u1, u3], ans)

    assert res.has_errors
    assert res.outcome == "needs_review"
    assert any(i.code == "V1_QUESTION_GAP" for i in res.issues)


def test_overrides_and_debug_render(tmp_path: Path):
    pdf_path = tmp_path / "render_test.pdf"
    _build_synthetic_suggested_answer_pdf(pdf_path)

    doc = fitz.open(str(pdf_path))
    lines = build_block_stream(doc)
    doc.close()

    profile = resolve_profile(Path("profiles"), "s2023", "suggested_answer")
    segmenter = Segmenter(profile=profile, doc_sha256="doc_render_sha")
    units = segmenter.segment(lines)
    answers = pair_answers(units, mode=profile.mode)

    # Apply override: patch Q1.a marks to 15
    override_data = {
        "mode": "patch",
        "units": [{"label_path": "Q1.a", "marks": 15}],
    }
    patched_units = apply_override(units, override_data)
    assert patched_units[0].children[0].marks == 15
    assert patched_units[0].children[0].marks_source == "override"

    # Render debug HTML
    val = DocumentValidator(profile=profile).validate(patched_units, answers)
    html_path = render_debug_html(
        doc_sha256="doc_render_sha",
        lines=lines,
        units=patched_units,
        validation=val,
        output_dir=tmp_path / "debug",
    )
    assert html_path.is_file()
    content = html_path.read_text(encoding="utf-8")
    assert "doc_render_sha" in content
    assert "Q1.a" in content


def test_pipeline_end_to_end(tmp_path: Path):
    # 1. Setup PDF and blob store
    pdf_path = tmp_path / "May_2024_Paper_1_Suggested_Answers.pdf"
    _build_synthetic_suggested_answer_pdf(pdf_path)

    settings = get_settings()
    blob_store = BlobStore(settings.storage.blob_dir)
    raw_bytes = pdf_path.read_bytes()
    sha256, path_written = blob_store.put(raw_bytes)
    num_bytes = len(raw_bytes)

    # 2. Insert confirmed document record
    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            sha256=sha256,
            blob_path=str(path_written),
            bytes=num_bytes,
            origin="manual",
            scheme_id="s2023",
            attempt_id="2024-05",
            paper_id="s2023.P1",
            doc_type_id="suggested_answer",
            title="May 2024 Paper 1 Suggested Answers",
            catalog_status="confirmed",
            extract_status="pending",
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    # 3. Run extraction pipeline
    pipeline = ExtractionPipeline(
        blob_store=blob_store,
        profiles_dir=Path("profiles"),
        overrides_dir=Path("overrides"),
        debug_dir=tmp_path / "debug",
    )

    with session_factory() as session:
        with open_run(stage="l2_extract", args={"doc_id": doc_id}) as run:
            summary = pipeline.extract_document(
                session=session,
                document_id=doc_id,
                run_id=run.id,
            )

            assert summary.document_id == doc_id
            assert summary.extract_status in ("ok", "ok_with_warnings")
            assert summary.total_units > 10
            assert summary.gradable_units >= 6

    # 4. Verify DB persistence
    with session_factory() as session:
        doc_check = session.get(Document, doc_id)
        assert doc_check.extract_status in ("ok", "ok_with_warnings")
        assert doc_check.page_count == 4
        assert doc_check.has_text_layer is True

        persisted_units = (
            session.query(Unit)
            .filter(Unit.document_id == doc_id, Unit.current.is_(True))
            .all()
        )
        assert len(persisted_units) > 10
        # Check hierarchy
        q1_unit = next(u for u in persisted_units if u.label_path == "Q1")
        q1a_unit = next(u for u in persisted_units if u.label_path == "Q1.a")
        assert q1a_unit.parent_unit_id == q1_unit.id
        assert q1a_unit.marks == 10
        assert q1a_unit.is_gradable is True

        # Check answers
        q1a_ans = session.get(UnitAnswer, q1a_unit.id)
        assert q1a_ans is not None
        assert "Ind AS 115" in (q1a_ans.answer_text or "")
        assert q1a_ans.pairing_method == "same_doc"
