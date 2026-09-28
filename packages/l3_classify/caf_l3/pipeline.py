"""L3 Classification pipeline selecting units and writing tag suggestions with resumability."""

from dataclasses import dataclass
import logging
from typing import Any
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from caf_db.models.core import Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit, UnitAnswer
from caf_l3.cascade import ClassificationResult, HierarchicalClassifier
from caf_l3.llm import GeminiClassifier, QuotaExhaustedError

logger = logging.getLogger(__name__)


@dataclass
class ClassificationSummary:
    total_processed: int
    buckets: dict[str, int]
    primary_suggestions: int
    secondary_suggestions: int
    is_partial: bool = False
    quota_exhausted: bool = False
    status_message: str = "Completed successfully."


class ClassificationPipeline:
    """Orchestrates L3 tag suggestion with LLM, immediate commits, and quota resilience."""

    def __init__(self, session: Session, model_override: str | None = None):
        self.session = session
        self.gemini_classifier = GeminiClassifier(session, model_override=model_override)
        self.classifier = HierarchicalClassifier(session, gemini_classifier=self.gemini_classifier)

    def run_classification(
        self,
        run_id: int,
        doc_id: int | None = None,
        paper_id: str | None = None,
        limit: int = 500,
        is_shadow: bool = False,
        resume: bool = True,
        use_llm: bool = True,
    ) -> ClassificationSummary:
        """Process pending gradable units and persist tag suggestions with per-unit commit."""
        # 1. Query candidate units with optional official answer text
        query = (
            select(Unit, Document, UnitAnswer.answer_text)
            .join(Document, Unit.document_id == Document.id)
            .outerjoin(UnitAnswer, Unit.id == UnitAnswer.unit_id)
            .where(
                Unit.current.is_(True),
                Unit.is_gradable.is_(True),
                Document.catalog_status == "confirmed",
                Document.extract_status.in_(["ok", "ok_with_warnings"]),
            )
        )

        if resume:
            query = query.where(Unit.classify_status.in_(["pending", "failed"]))
        else:
            query = query.where(Unit.classify_status.in_(["pending", "failed", "suggested"]))

        if doc_id is not None:
            query = query.where(Document.id == doc_id)
        if paper_id is not None:
            query = query.where(Document.paper_id == paper_id)

        query = query.order_by(Document.attempt_id.desc(), Unit.id.asc()).limit(limit)
        results = self.session.execute(query).all()

        bucket_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_primary = 0
        total_secondary = 0
        processed_count = 0
        quota_hit = False

        # Preload already decided fingerprints to avoid reclassifying curated items
        decided_fps = set(
            self.session.scalars(select(Decision.unit_fingerprint)).all()
        )

        # Preload already suggested unit IDs if resuming
        already_suggested_ids = set()
        if resume:
            already_suggested_ids = set(
                self.session.scalars(select(TagSuggestion.unit_id).distinct()).all()
            )

        for unit, doc, answer_text in results:
            if unit.fingerprint in decided_fps:
                continue

            if resume and unit.id in already_suggested_ids:
                continue

            try:
                # Classify (passes answer text if available)
                res: ClassificationResult = self.classifier.classify_unit(
                    paper_id=doc.paper_id or "s2023.P1",
                    question_text=unit.question_text,
                    answer_text=answer_text or "",
                    chapter_hint_id=doc.chapter_hint_node_id,
                    fingerprint=unit.fingerprint,
                    run_id=run_id,
                    use_llm=use_llm,
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

                # Commit per-unit immediately to ensure zero data loss on quota exhaustion
                self.session.commit()

            except QuotaExhaustedError as q_err:
                logger.warning("Quota exhausted on unit ID %s: %s", unit.id, q_err)
                quota_hit = True
                self.session.rollback()
                break

            except Exception as e:
                logger.error("Error classifying unit ID %s: %s", unit.id, e)
                unit.classify_status = "failed"
                self.session.commit()
                continue

        status_msg = "Completed successfully."
        if quota_hit:
            status_msg = (
                f"Google Gemini daily quota / rate limit reached. "
                f"Successfully saved {processed_count} units before stopping. "
                f"Re-run with '--resume' once your quota resets to continue seamlessly."
            )

        return ClassificationSummary(
            total_processed=processed_count,
            buckets=bucket_counts,
            primary_suggestions=total_primary,
            secondary_suggestions=total_secondary,
            is_partial=quota_hit,
            quota_exhausted=quota_hit,
            status_message=status_msg,
        )
