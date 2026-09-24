"""L3 Classification pipeline selecting units and writing tag suggestions."""

from dataclasses import dataclass
from typing import Any
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_l3.cascade import ClassificationResult, HierarchicalClassifier


@dataclass
class ClassificationSummary:
    total_processed: int
    buckets: dict[str, int]
    primary_suggestions: int
    secondary_suggestions: int


class ClassificationPipeline:
    """Orchestrates L3 tag suggestion and consistency protocol."""

    def __init__(self, session: Session):
        self.session = session
        self.classifier = HierarchicalClassifier(session)

    def run_classification(
        self,
        run_id: int,
        doc_id: int | None = None,
        paper_id: str | None = None,
        limit: int = 500,
        is_shadow: bool = False,
    ) -> ClassificationSummary:
        """Process pending gradable units and persist tag suggestions."""
        # 1. Query candidate units
        query = (
            select(Unit, Document)
            .join(Document, Unit.document_id == Document.id)
            .where(
                Unit.current.is_(True),
                Unit.is_gradable.is_(True),
                Unit.classify_status.in_(["pending", "failed"]),
                Document.catalog_status == "confirmed",
                Document.extract_status.in_(["ok", "ok_with_warnings"]),
            )
        )

        if doc_id is not None:
            query = query.where(Document.id == doc_id)
        if paper_id is not None:
            query = query.where(Document.paper_id == paper_id)

        query = query.limit(limit)
        results = self.session.execute(query).all()

        bucket_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_primary = 0
        total_secondary = 0
        processed_count = 0

        # Preload decided fingerprints to avoid reclassifying
        decided_fps = set(
            self.session.scalars(select(Decision.unit_fingerprint)).all()
        )

        for unit, doc in results:
            if unit.fingerprint in decided_fps:
                continue

            # Classify
            res: ClassificationResult = self.classifier.classify_unit(
                paper_id=doc.paper_id or "s2023.P1",
                question_text=unit.question_text,
                answer_text="",  # Extracted in unit_answer or parsed
                chapter_hint_id=doc.chapter_hint_node_id,
                fingerprint=unit.fingerprint,
            )

            # Persist Primary Suggestion
            prim_sugg = TagSuggestion(
                unit_id=unit.id,
                run_id=run_id,
                node_id=res.primary_node_id,
                role="primary",
                method=res.method,
                bucket=res.bucket,
                evidence={
                    **res.evidence,
                    "justification": res.justification,
                    "gist": res.gist,
                    "alternatives": res.alternatives,
                },
                is_shadow=is_shadow,
            )
            self.session.add(prim_sugg)
            total_primary += 1

            # Persist Secondary Suggestions
            for sec_node_id in res.secondary_node_ids:
                sec_sugg = TagSuggestion(
                    unit_id=unit.id,
                    run_id=run_id,
                    node_id=sec_node_id,
                    role="secondary",
                    method=res.method,
                    bucket=res.bucket,
                    evidence={"primary_ref": res.primary_node_id},
                    is_shadow=is_shadow,
                )
                self.session.add(sec_sugg)
                total_secondary += 1

            # Update unit status if not shadow run
            if not is_shadow:
                unit.classify_status = "suggested"

            bucket_counts[res.bucket] = bucket_counts.get(res.bucket, 0) + 1
            processed_count += 1

        self.session.commit()

        return ClassificationSummary(
            total_processed=processed_count,
            buckets=bucket_counts,
            primary_suggestions=total_primary,
            secondary_suggestions=total_secondary,
        )
