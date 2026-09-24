"""Milestone 2 Acquisition and Catalogue Test Suite."""

from pathlib import Path
import fitz
import pytest
from fastapi.testclient import TestClient

from caf_api.main import app
from caf_common.blob_store import BlobStore
from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.ingest import Document
from caf_l1.importer import ManualImporter
from caf_l1.infer import infer_metadata

client = TestClient(app)


def test_metadata_inference():
    # 1. Suggested Answer
    t1 = infer_metadata(
        url="https://resource.cdn.icai.org/12345may24_p1_sa.pdf",
        anchor_text="Paper 1: Financial Reporting Suggested Answers May 2024",
    )
    assert t1["attempt_id"] == "2024-05"
    assert t1["paper_id"] == "s2023.P1"
    assert t1["doc_type_id"] == "suggested_answer"
    assert t1["catalog_status"] == "inferred"

    # 2. Question Paper
    t2 = infer_metadata(
        url="https://resource.cdn.icai.org/sep2025_dt_qp.pdf",
        anchor_text="September 2025 Paper 4 Direct Tax Laws Question Paper",
    )
    assert t2["attempt_id"] == "2025-09"
    assert t2["paper_id"] == "s2023.P4"
    assert t2["doc_type_id"] == "question_paper"
    assert t2["catalog_status"] == "inferred"

    # 3. RTP
    t3 = infer_metadata(
        url="https://resource.cdn.icai.org/rtp_nov24_p5.pdf",
        anchor_text="Revision Test Paper November 2024 Paper 5",
    )
    assert t3["attempt_id"] == "2024-11"
    assert t3["paper_id"] == "s2023.P5"
    assert t3["doc_type_id"] == "rtp"
    assert t3["catalog_status"] == "inferred"

    # 4. MTP with series
    t4 = infer_metadata(
        url="https://resource.cdn.icai.org/mtp_p2_ans_may25.pdf",
        anchor_text="Mock Test Paper Series 1 Answer May 2025 Advanced Financial Management",
    )
    assert t4["attempt_id"] == "2025-05"
    assert t4["paper_id"] == "s2023.P2"
    assert t4["doc_type_id"] == "mtp_answer"
    assert t4["series"] == "1"
    assert t4["catalog_status"] == "inferred"


def test_manual_importer_and_curate_api(tmp_path: Path):
    # 1. Create a dummy test PDF
    pdf_path = tmp_path / "May_2024_Paper_1_Financial_Reporting_suggested_answer.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "THE INSTITUTE OF CHARTERED ACCOUNTANTS OF INDIA\nSUGGESTED ANSWERS MAY 2024\nFINANCIAL REPORTING")
    doc.save(str(pdf_path))
    doc.close()

    # 2. Import into blob store and DB
    settings = get_settings()
    blob_store = BlobStore(settings.storage.blob_dir)
    importer = ManualImporter(blob_store=blob_store)

    session_factory = get_session_factory()
    with session_factory() as session:
        imported_doc = importer.import_file(pdf_path, session)
        doc_id = imported_doc.id
        assert doc_id is not None
        assert imported_doc.origin == "manual"
        assert imported_doc.attempt_id == "2024-05"
        assert imported_doc.paper_id == "s2023.P1"
        assert imported_doc.doc_type_id == "suggested_answer"
        assert imported_doc.catalog_status == "inferred"
        assert blob_store.exists(imported_doc.sha256)

    # 3. List documents in Curator API
    res = client.get("/api/v1/curate/documents?status=inferred")
    assert res.status_code == 200
    docs = res.json()
    assert any(d["id"] == doc_id for d in docs)

    # 4. Confirm document via Curator API
    confirm_res = client.post(f"/api/v1/curate/documents/{doc_id}/confirm")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["catalog_status"] == "confirmed"

    # 5. Verify status updated in database
    with session_factory() as session:
        d_check = session.get(Document, doc_id)
        assert d_check.catalog_status == "confirmed"
