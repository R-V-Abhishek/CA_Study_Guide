"""Seed a conservative completeness ledger from acquired inventory evidence."""
import json
from collections import defaultdict
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_db.models.intel import CorpusCoverage
from caf_db.models.ref import Attempt, Paper
from caf_db.models.questions import PublishedQuestion, QuestionOccurrence
from caf_db.models.classification import QuestionPublication


def seed_coverage(session: Session, taxonomy_version_id: int,
                  source_coverage: Path = Path("docs/Phase4_Source_Coverage.json")) -> dict:
    """Existing inventory is partial; never infer expected scope or human approval.

    Phase 4's continuation queue is rendered from these per-record outcomes and
    reasons, which remain explicit blockers in the ledger.
    """
    evidence = json.loads(source_coverage.read_text())
    records = evidence["records"]
    known_papers = set(session.scalars(sa.select(Paper.id)))
    known_attempts = set(session.scalars(sa.select(Attempt.id)))
    grouped = defaultdict(dict)
    skipped = {"undated": 0, "unresolved_identity": 0, "outside_corpus": 0}
    for record in records:
        if record["course_level"].lower() != "final" or record["scheme_id"] != "s2023":
            skipped["outside_corpus"] += 1
            continue
        if record["attempt_id"] is None:
            skipped["undated"] += 1
            continue
        if record["paper_id"] not in known_papers or record["attempt_id"] not in known_attempts:
            skipped["unresolved_identity"] += 1
            continue
        grouped[(record["paper_id"], record["attempt_id"], record["source_family"])][record["inventory_id"]] = record
    publications = session.execute(sa.select(PublishedQuestion, QuestionOccurrence).join(
        QuestionPublication, QuestionPublication.current_snapshot_id == PublishedQuestion.id).join(
        QuestionOccurrence, QuestionOccurrence.id == PublishedQuestion.occurrence_id).where(
        PublishedQuestion.taxonomy_version_id == taxonomy_version_id)).all()
    created = existing = 0
    for (paper_id, attempt_id, family), rows in grouped.items():
        key = (taxonomy_version_id, paper_id, attempt_id, family)
        if session.get(CorpusCoverage, key):
            existing += 1
            continue
        bound = [publication for publication, occurrence in publications if
                 (occurrence.paper_id, occurrence.attempt_id, occurrence.source_family) == (paper_id, attempt_id, family)]
        blockers = ["expected_inventory_unreviewed", "official_scope_review_pending"]
        blockers.extend(sorted({row["reason"] for row in rows.values() if row.get("reason")}))
        session.add(CorpusCoverage(taxonomy_version_id=taxonomy_version_id, paper_id=paper_id,
            attempt_id=attempt_id, source_family=family, inventory_reviewed=False,
            expected_slots=None, discovered_count=len(rows),
            acquired_count=sum(bool(row["artifact_acquired"]) for row in rows.values()),
            reviewed_roots=len(bound), reviewed_parts=sum(len(publication.mappings) for publication in bound),
            published_roots=len(bound), missing_answers=sum(publication.content["answer_status"] == "missing"
                                                         for publication in bound), blockers=blockers))
        created += 1
    session.commit()
    return {"created": created, "preserved_existing": existing, "skipped": skipped,
            "expected_inventory": "unknown", "human_approvals_created": 0}
