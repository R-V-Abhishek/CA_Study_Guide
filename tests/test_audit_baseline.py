"""Provenance evidence and read-only baseline contracts."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import event, select, text
from typer.testing import CliRunner

from caf_common.audit import collect_baseline, write_baseline
from caf_db.engine import get_engine, get_session_factory
from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_db.models.ingest import DiscoveredLink, Document, TagSuggestion, Unit
from caf_db.models.ref import Node


def _document(db, tmp_path, *, title="Local source", official=False):
    content = title.encode()
    source = tmp_path / f"{hashlib.sha256(content).hexdigest()}.pdf"
    source.write_bytes(content)
    doc = Document(sha256=hashlib.sha256(content).hexdigest(), blob_path=str(source),
                   bytes=len(content), origin="manual", paper_id="s2023.P1",
                   attempt_id="2024-05", doc_type_id="suggested_answer", title=title,
                   catalog_status="confirmed", extract_status="ok", created_run_id=1)
    db.add(doc)
    db.flush()
    if official:
        db.add(DiscoveredLink(url=f"https://resource.cdn.icai.org/{doc.sha256}.pdf", document_id=doc.id,
                              link_status="downloaded", inferred={}))
    return doc


def _unit(db, document, fingerprint):
    unit = Unit(document_id=document.id, extract_run_id=1, label_path="Q1(a)",
                display_label="Q1(a)", kind="part", is_gradable=True, marks=10,
                page_start=1, page_end=1, block_start="p1b1", block_end="p1b2",
                question_text="Question with unrecorded answer", text_origin="pdf",
                fingerprint=fingerprint, parse_confidence="high", validation_flags=[], current=True)
    db.add(unit)
    db.flush()
    return unit


def test_baseline_evidence_read_only_and_reports(tmp_path):
    factory = get_session_factory()
    with factory() as db:
        authentic = _document(db, tmp_path, title="Official test of controls question", official=True)
        unresolved = _document(db, tmp_path, title="test in filename is not proof")
        altered = _document(db, tmp_path, title="Altered official source", official=True)
        Path(altered.blob_path).write_bytes(b"changed after ingestion")
        synthetic = Document(sha256="test_classify_abc", blob_path="/tmp/fake_classify.pdf",
                             bytes=1000, origin="manual", title="Classify Test Document",
                             paper_id="s2023.P1", attempt_id="2024-05", doc_type_id="suggested_answer",
                             catalog_status="confirmed", extract_status="ok")
        db.add(synthetic)
        unit = _unit(db, authentic, "a" * 40)
        default_node = db.get(Node, "P1-PZR6WV")
        assert default_node is not None
        cross_node = db.scalars(select(Node).where(Node.paper_id == "s2023.P2", Node.level == "subtopic")).first()
        assert cross_node is not None
        db.execute(text("DELETE FROM ref.descriptor WHERE node_id=:node_id"), {"node_id": cross_node.id})
        missing_descriptor_id = cross_node.id
        db.add_all([
            TagSuggestion(unit_id=unit.id, run_id=1, node_id=default_node.id, role="primary",
                          method="llm", model_id="agent-semantic-v1", bucket="C",
                          evidence={"core_concept": "General financial reporting concept", "confidence": 0.60}),
            TagSuggestion(unit_id=unit.id, run_id=1, node_id=cross_node.id, role="secondary",
                          method="anchor", bucket="B", evidence={}),
        ])
        decision = Decision(unit_fingerprint=unit.fingerprint, action="accept", payload={}, suggestion_run_id=1)
        db.add(decision)
        db.flush()
        appearance = Appearance(unit_fingerprint=unit.fingerprint, source_unit_id=unit.id,
                                doc_sha256=authentic.sha256, attempt_id="2024-05", source_paper_id="s2023.P1",
                                doc_type_id="suggested_answer", signal_class="exam", display_label="Q1(a)",
                                marks=10, gist="Published item", page_start=1, page_end=1, status="published")
        db.add(appearance)
        db.flush()
        db.add(AppearanceTag(appearance_id=appearance.id, node_id=default_node.id,
                             role="primary", share=1.0, decision_id=decision.id))
        db.commit()
        ids = authentic.id, unresolved.id, altered.id, synthetic.id
    engine = get_engine()
    statements = []

    def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        first = collect_baseline(engine)
        second = collect_baseline(engine)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
        engine.dispose()
    assert first["table_counts"] == second["table_counts"]
    assert first["documents"] == second["documents"]
    assert first["database_transaction"]["read_only"] == "on"
    assert first["database_transaction"]["isolation"] == "repeatable read"
    assert all(sql.lstrip().startswith(("SELECT", "SET TRANSACTION READ ONLY", "SET LOCAL TIME ZONE 'UTC'")) for sql in statements)
    docs = {doc["id"]: doc for doc in first["documents"]}
    assert docs[ids[0]]["category"] == "authentic source identified"
    assert docs[ids[1]]["category"] == "unresolved provenance"
    assert docs[ids[2]]["category"] == "unresolved provenance"
    assert docs[ids[2]]["source_file"]["status"] == "checksum_mismatch"
    assert docs[ids[3]]["category"] == "confirmed synthetic"
    assert any("Forced default" in reason for suggestion in first["audited_suggestions"] for reason in suggestion["questionable_reasons"])
    assert any("Unexpected cross-paper" in reason for suggestion in first["audited_suggestions"] for reason in suggestion["questionable_reasons"])
    assert len(first["questionable_published_appearances"]) == 1
    assert first["lineage"]["current_gradable_units_without_answers"]
    assert first["lineage"]["published_reference_issues"] == []
    assert any("reviewer identity" in limitation for limitation in first["limitations"])
    assert "PostgreSQL-enforced read-only" in first["source_database_policy"]
    completeness = first["taxonomy_completeness"]
    assert sum(group["count"] for group in completeness["nodes_by_paper_level"]) == first["table_counts"]["ref.node"]
    assert sum(group["count"] for group in completeness["descriptors_by_approval_source"]) == first["table_counts"]["ref.descriptor"]
    assert missing_descriptor_id in {row["node_id"] for row in completeness["subtopics_missing_descriptors"]}
    confidence_counts = {row["confidence_bucket"]: row["count"] for row in first["confidence_groups"]}
    assert confidence_counts["[0.50,0.80)"] == 1
    assert confidence_counts["absent"] == 1
    assert "never inferred" in first["confidence_scale"]
    folder = write_baseline(first, tmp_path / "audits")
    next_folder = write_baseline(first, tmp_path / "audits")
    assert folder != next_folder
    assert json.loads((folder / "baseline.json").read_text())["report_version"] == "phase0.provenance.v1"
    assert "confirmed synthetic" in (folder / "baseline.md").read_text()


def test_audit_cli_uses_read_only_baseline(tmp_path):
    from caf_cli.main import app

    with get_session_factory()() as db:
        before = db.execute(text("SELECT count(*) FROM ops.run")).scalar_one()
    result = CliRunner().invoke(app, ["audit", "baseline", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Provenance baseline:" in result.output
    reports = list(tmp_path.glob("*/baseline.json"))
    assert len(reports) == 1
    with get_session_factory()() as db:
        assert db.execute(text("SELECT count(*) FROM ops.run")).scalar_one() == before


def test_audit_checkpoint_comparison_detects_personal_content_changes(session, tmp_path):
    from caf_common.backup import create_backup
    from caf_cli.main import app
    from caf_db.models.app import Note

    checkpoint = create_backup(backup_dir=tmp_path / "backups")
    arguments = ["audit", "baseline", "--output-dir", str(tmp_path / "audits"),
                 "--checkpoint-manifest", str(checkpoint.manifest_file)]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    session.add(Note(user_id=1, node_id="P1-WB29V3", body="New personal note"))
    session.commit()
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 1
    reports = [json.loads(path.read_text()) for path in (tmp_path / "audits").glob("*/baseline.json")]
    changed = next(report for report in reports if not report["checkpoint_comparison"]["unchanged"])
    assert changed["checkpoint_comparison"]["mismatches"] == ["app.note"]
