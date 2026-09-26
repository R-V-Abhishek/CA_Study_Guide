"""Milestone 4 Classification and Curation Test Suite."""

import uuid
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from caf_api.main import app
from caf_common.run_context import open_run
from caf_db.engine import get_session_factory
from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.ref import Anchor, Descriptor, Node
from caf_l3.anchors import extract_anchors, lookup_anchor_candidates
from caf_l3.cascade import HierarchicalClassifier
from caf_l3.pipeline import ClassificationPipeline
from caf_l4.publish import bulk_accept_bucket_a, compute_law_stale, make_decision

client = TestClient(app)


def test_anchors_extraction_and_lookup():
    session_factory = get_session_factory()
    with session_factory() as session:
        # 1. Test P1: Ind AS extraction
        p1_text = "XYZ Ltd is applying Ind AS 115 for customer contract and Ind AS 116 for warehouse lease."
        matches = extract_anchors(p1_text, "P1")
        assert len(matches) == 2
        keys = {m.ref_key for m in matches}
        assert "115" in keys
        assert "116" in keys

        candidates = lookup_anchor_candidates(session, matches)
        assert len(candidates) >= 2
        # Ind AS 116 chapter is P1-093VHQ, Ind AS 115 chapter is P1-P425DG
        assert "P1-093VHQ" in candidates
        assert "P1-P425DG" in candidates

        # 2. Test P3: SA extraction
        p3_text = "As per SA 700 and SA 240, auditor should consider fraud risks and KAM."
        sa_matches = extract_anchors(p3_text, "P3")
        assert any(m.ref_key == "700" for m in sa_matches)
        assert any(m.ref_key == "240" for m in sa_matches)

        sa_candidates = lookup_anchor_candidates(session, sa_matches)
        assert len(sa_candidates) >= 2

        # 3. Test P4: Section extraction
        p4_text = "Calculate depreciation under Section 32 and business deduction under Section 37."
        p4_matches = extract_anchors(p4_text, "P4")
        assert any(m.ref_key == "32" for m in p4_matches)
        assert any(m.ref_key == "37" for m in p4_matches)

        p4_candidates = lookup_anchor_candidates(session, p4_matches)
        assert len(p4_candidates) >= 1

        # 4. Test P5: GST section extraction
        p5_text = "Assess liability under Section 7 and credit under Section 16 of CGST Act."
        p5_matches = extract_anchors(p5_text, "P5")
        assert any(m.ref_key == "7" and m.instrument_id == "CGST" for m in p5_matches)
        assert any(m.ref_key == "16" and m.instrument_id == "CGST" for m in p5_matches)


def test_classification_cascade_and_consistency():
    session_factory = get_session_factory()
    with session_factory() as session:
        classifier = HierarchicalClassifier(session)

        # Question on Ind AS 115
        q_text = "Explain the 5-step model for revenue recognition from contracts with customers under Ind AS 115."
        ans_text = "Under Ind AS 115, an entity recognizes revenue by identifying contract, performance obligations..."
        res = classifier.classify_unit(
            paper_id="s2023.P1",
            question_text=q_text,
            answer_text=ans_text,
            fingerprint="test_fp_115",
        )

        assert res.primary_node_id in ("P1-P425DG", "P1-1Y2TGB") or "P1-" in res.primary_node_id
        # Since Ind AS 115 anchor matches and R1=R2 agree, bucket should be A
        assert res.bucket == "A"
        assert res.method in ("anchor", "llm", "structure")
        assert len(res.gist.split()) <= 25


def test_classification_pipeline_persistence():
    uid = uuid.uuid4().hex[:12]
    session_factory = get_session_factory()
    with session_factory() as session:
        # Create a confirmed document with a gradable unit
        doc = Document(
            sha256=f"test_classify_{uid}",
            blob_path="/tmp/fake_classify.pdf",
            bytes=1000,
            origin="manual",
            scheme_id="s2023",
            attempt_id="2024-05",
            paper_id="s2023.P1",
            doc_type_id="suggested_answer",
            title="Classify Test Document",
            catalog_status="confirmed",
            extract_status="ok",
        )
        session.add(doc)
        session.flush()

        unit = Unit(
            document_id=doc.id,
            extract_run_id=1,
            label_path="Q1.a",
            display_label="1(a)",
            kind="part",
            is_gradable=True,
            marks=10,
            marks_source="explicit",
            page_start=1,
            page_end=1,
            block_start="p1-b1",
            block_end="p1-b5",
            question_text="Assess ROU asset and lease liability accounting under Ind AS 116 for a 5-year lease.",
            text_origin="pdf",
            fingerprint=f"test_fp_pipeline_{uid}",
            parse_confidence="high",
            classify_status="pending",
            current=True,
        )
        session.add(unit)
        session.commit()
        unit_id = unit.id
        doc_id = doc.id

    # Run classification pipeline
    with session_factory() as session:
        with open_run(stage="l3_classify", args={"doc_id": doc_id}) as run:
            pipeline = ClassificationPipeline(session)
            summary = pipeline.run_classification(run_id=run.id, doc_id=doc_id)

            assert summary.total_processed >= 1
            assert summary.primary_suggestions >= 1

    # Verify suggestions and unit status
    with session_factory() as session:
        u_check = session.get(Unit, unit_id)
        assert u_check.classify_status == "suggested"

        suggs = session.query(TagSuggestion).filter(TagSuggestion.unit_id == unit_id).all()
        assert len(suggs) >= 1
        prim = next(s for s in suggs if s.role == "primary")
        assert prim.bucket in ("A", "B")
        assert "P1-" in prim.node_id


def test_curation_api_and_publishing():
    uid = uuid.uuid4().hex[:12]
    session_factory = get_session_factory()
    with session_factory() as session:
        # Create doc + unit + tag suggestion
        doc = Document(
            sha256=f"test_curate_{uid}",
            blob_path="/tmp/fake_curate.pdf",
            bytes=2000,
            origin="manual",
            scheme_id="s2023",
            attempt_id="2024-05",
            paper_id="s2023.P1",
            doc_type_id="suggested_answer",
            title="Curate Test Document",
            catalog_status="confirmed",
            extract_status="ok",
        )
        session.add(doc)
        session.flush()

        unit = Unit(
            document_id=doc.id,
            extract_run_id=1,
            label_path="Q2.a",
            display_label="2(a)",
            kind="part",
            is_gradable=True,
            marks=12,
            marks_source="explicit",
            page_start=2,
            page_end=2,
            block_start="p2-b1",
            block_end="p2-b8",
            question_text="Business combinations under Ind AS 103: purchase consideration and goodwill.",
            text_origin="pdf",
            fingerprint=f"test_fp_curate_{uid}",
            parse_confidence="high",
            classify_status="suggested",
            current=True,
        )
        session.add(unit)
        session.flush()

        sugg = TagSuggestion(
            unit_id=unit.id,
            run_id=1,
            node_id="P1-WB29V3",  # Ind AS 103 chapter
            role="primary",
            method="anchor",
            bucket="A",
            evidence={"gist": "Accounting for business combination and goodwill"},
        )
        session.add(sugg)
        session.commit()
        unit_id = unit.id
        doc_id = doc.id

    # 1. GET /api/v1/curate/queue
    res = client.get("/api/v1/curate/queue")
    assert res.status_code == 200
    queue_items = res.json()
    assert any(item["unit_id"] == unit_id for item in queue_items)

    # 2. POST /api/v1/curate/units/{unit_id}/decision
    decision_payload = {
        "action": "accept",
        "primary_node_id": "P1-WB29V3",
        "secondary_node_ids": [],
        "gist": "Business combination purchase consideration and goodwill",
        "seconds_spent": 8.0,
    }
    dec_res = client.post(f"/api/v1/curate/units/{unit_id}/decision", json=decision_payload)
    assert dec_res.status_code == 200
    assert dec_res.json()["action"] == "accept"

    # 3. Verify published appearance in database
    with session_factory() as session:
        u_check = session.get(Unit, unit_id)
        assert u_check.classify_status == "decided"

        app = session.query(Appearance).filter(Appearance.unit_fingerprint == f"test_fp_curate_{uid}").first()
        assert app is not None
        assert app.status == "published"
        assert app.marks == 12

        tags = session.query(AppearanceTag).filter(AppearanceTag.appearance_id == app.id).all()
        assert len(tags) == 1
        assert tags[0].node_id == "P1-WB29V3"
        assert tags[0].role == "primary"
        assert tags[0].share == 1.0

        cl = session.query(ChangeLog).filter(ChangeLog.entity_id == str(app.id)).first()
        assert cl is not None
        assert cl.change == "publish"


def test_bulk_accept_bucket_a():
    uid = uuid.uuid4().hex[:12]
    session_factory = get_session_factory()
    with session_factory() as session:
        doc = Document(
            sha256=f"test_bulk_{uid}",
            blob_path="/tmp/fake_bulk.pdf",
            bytes=3000,
            origin="manual",
            scheme_id="s2023",
            attempt_id="2024-05",
            paper_id="s2023.P1",
            doc_type_id="suggested_answer",
            title="Bulk Accept Test Document",
            catalog_status="confirmed",
            extract_status="ok",
        )
        session.add(doc)
        session.flush()

        for idx in range(1, 4):
            u = Unit(
                document_id=doc.id,
                extract_run_id=1,
                label_path=f"Q{idx}.a",
                display_label=f"{idx}(a)",
                kind="part",
                is_gradable=True,
                marks=10,
                page_start=idx,
                page_end=idx,
                block_start=f"p{idx}-b1",
                block_end=f"p{idx}-b5",
                question_text=f"Question {idx} testing standards",
                text_origin="pdf",
                fingerprint=f"test_fp_bulk_{uid}_{idx}",
                parse_confidence="high",
                classify_status="suggested",
                current=True,
            )
            session.add(u)
            session.flush()

            session.add(
                TagSuggestion(
                    unit_id=u.id,
                    run_id=1,
                    node_id="P1-093VHQ",
                    role="primary",
                    method="anchor",
                    bucket="A",
                    evidence={"gist": f"Gist {idx}"},
                )
            )

        session.commit()
        doc_id = doc.id

    # Call bulk accept endpoint
    res = client.post(f"/api/v1/curate/documents/{doc_id}/bulk_accept_bucket_a")
    assert res.status_code == 200
    assert res.json()["accepted_count"] == 3

    with session_factory() as session:
        # All 3 units should be decided and published
        apps = session.query(Appearance).filter(Appearance.doc_sha256 == f"test_bulk_{uid}").all()
        assert len(apps) == 3
        assert all(a.status == "published" for a in apps)


def test_law_staleness():
    """Verify compute_law_stale covers exclude policy (→ False) and mark_stale policy (→ True).

    Seed data (taxonomy/registry/law_boundaries.yaml):
      - gst_intro: P5, policy=exclude, first_applicable_attempt=2018-05
      - ita_2025: P4, policy=mark_stale, first_applicable_attempt=null
        (null means the boundary has no attempt threshold yet — so it never fires)

    To test the mark_stale=True path we insert a temporary boundary with a real threshold.
    """
    from caf_db.models.ref import LawBoundary

    session_factory = get_session_factory()
    with session_factory() as session:
        # 1. EXCLUDE policy: pre-GST attempt in P5 should be False (policy is 'exclude', not 'mark_stale')
        is_stale_exclude = compute_law_stale(session, "2017-05", "s2023.P5", ["P5-4RKS1C"])
        assert is_stale_exclude is False, (
            "gst_intro boundary has policy=exclude, not mark_stale — should return False"
        )

        # 2. Current attempt in P5 (post-GST): also False
        assert compute_law_stale(session, "2024-05", "s2023.P5", ["P5-4RKS1C"]) is False

        # 3. P4 with null first_applicable_attempt: never stale (guard in code skips it)
        assert compute_law_stale(session, "2024-05", "s2023.P4", ["P4-XXXXXX"]) is False, \
            "ita_2025 has null first_applicable_attempt — should not fire"

        # 4. MARK_STALE path: insert a boundary with a real threshold and verify True
        test_boundary = LawBoundary(
            id="test_mark_stale_boundary",
            paper_code="P1",
            instrument_id="ITA1961",
            first_applicable_attempt="2025-05",  # attempts before 2025-05 become stale
            scope_node_ids=None,
            policy="mark_stale",
            description="Test boundary for mark_stale path verification",
        )
        session.add(test_boundary)
        session.commit()

        # Attempt "2024-05" < "2025-05" → should be stale
        is_stale_before = compute_law_stale(session, "2024-05", "s2023.P1", ["P1-093VHQ"])
        assert is_stale_before is True, (
            "Attempt 2024-05 is before first_applicable_attempt 2025-05 — should be mark_stale=True"
        )

        # Attempt "2025-05" >= "2025-05" → NOT stale (not strictly before the boundary)
        is_stale_at = compute_law_stale(session, "2025-05", "s2023.P1", ["P1-093VHQ"])
        assert is_stale_at is False, "Attempt exactly at boundary should not be stale"

        # Attempt "2025-11" > "2025-05" → NOT stale
        is_stale_after = compute_law_stale(session, "2025-11", "s2023.P1", ["P1-093VHQ"])
        assert is_stale_after is False

        # Cleanup: remove test boundary to avoid affecting other tests
        session.delete(test_boundary)
        session.commit()
