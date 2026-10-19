"""The recovery checkpoint contains the complete classification event history."""

import json

import sqlalchemy as sa

from caf_common.backup import create_backup, verify_backup
from caf_db.models.classification import (
    SuggestionRevision, ClassificationRevision, QuestionPublication,
    ClassificationEvent, ClassificationVerification, ClassificationDispute,
)
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_db.models.ref import TaxonomyVersion


def test_classification_history_survives_backup_restore(session, tmp_path):
    document = Document(sha256="phase5-recovery-synthetic", blob_path="fixture.pdf", bytes=0,
                        origin="manual", paper_id="s2023.P1")
    session.add(document)
    session.flush()
    extraction = ExtractionRevision(document_id=document.id, run_id=1, status="candidate",
                                    content_digest="a" * 64, profile_id="synthetic-recovery",
                                    configuration={}, quality={}, questions=[], parsed_units=[])
    session.add(extraction)
    session.flush()
    taxonomy_id = session.scalar(sa.select(TaxonomyVersion.id).order_by(TaxonomyVersion.id))
    mapping = [{"part_id": "synthetic-root", "outcome": "none_fits",
                "primary_node_id": None, "secondary_node_ids": [], "evidence": {},
                "confidence": None, "bucket": None, "excluded": False}]
    suggestion = SuggestionRevision(batch_key="synthetic-recovery", input_hash="b" * 64,
        document_id=document.id, extraction_revision_id=extraction.id,
        question_id="synthetic-root", taxonomy_version_id=taxonomy_id, run_id=1,
        experimental=True, context={}, candidates=[], mappings=mapping,
        provenance={"method": "synthetic-recovery-fixture"})
    session.add(suggestion)
    session.flush()
    reviewed = ClassificationRevision(question_id="synthetic-root",
        suggestion_revision_id=suggestion.id, extraction_revision_id=extraction.id,
        taxonomy_version_id=taxonomy_id, mappings=mapping, context={},
        input_hash=suggestion.input_hash, actor_id=1, blind=True)
    session.add(reviewed)
    session.flush()
    session.add_all([
        QuestionPublication(question_id="synthetic-root", document_id=document.id,
                            current_revision_id=None),
        ClassificationVerification(revision_id=reviewed.id, actor_id=1, active=False),
        ClassificationDispute(question_id="synthetic-root", revision_id=reviewed.id,
            actor_id=1, reason="Synthetic recovery fixture", status="dismissed",
            resolved_by=1, resolution_reason="Synthetic resolution"),
        ClassificationEvent(question_id="synthetic-root", revision_id=reviewed.id,
            actor_id=1, kind="withdraw", idempotency_key="synthetic-withdraw",
            request_hash="c" * 64, payload={"synthetic": True}),
    ])
    session.commit()
    checkpoint = create_backup(backup_dir=tmp_path)
    manifest = json.loads(checkpoint.manifest_file.read_text())
    for table in ("ingest.suggestion_revision", "core.classification_revision",
                  "core.question_publication", "core.classification_event",
                  "core.classification_verification", "core.classification_dispute"):
        assert manifest["tables"][table]["count"] == 1
    result = verify_backup(dump_file=checkpoint.dump_file)
    assert result.verified, result.message
    assert result.restored_counts == result.live_counts
