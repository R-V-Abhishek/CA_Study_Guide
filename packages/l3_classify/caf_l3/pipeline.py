"""L3 Classification pipeline selecting units and writing tag suggestions with resumability."""

from dataclasses import dataclass
import logging
from typing import Any
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from caf_db.models.ingest import Document, TagSuggestion, TaxonomyGap, Unit, UnitAnswer
from caf_db.models.ops import Run
from caf_db.models.ref import DocType, Paper
from caf_l3.cascade import ClassificationResult
from caf_l3.llm import GeminiClassifier, QuotaExhaustedError
from caf_l3.textbook import NeedsTaxonomyReview, TextbookClassifier

logger = logging.getLogger(__name__)


@dataclass
class ClassificationSummary:
    total_processed: int
    buckets: dict[str, int]
    primary_suggestions: int
    secondary_suggestions: int
    is_partial: bool = False
    quota_exhausted: bool = False
    failed_units: int = 0
    status_message: str = "Completed successfully."


class ClassificationPipeline:
    """Orchestrates L3 tag suggestion with LLM, immediate commits, and quota resilience."""

    def __init__(self, session: Session, model_override: str | None = None,
                 version_id: str | None = None):
        self.session = session
        self.gemini_classifier = GeminiClassifier(session, model_override=model_override)
        self.classifier = TextbookClassifier(session, version_id=version_id,
                                            gemini_classifier=self.gemini_classifier)

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
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown classification run: {run_id}")
        if run.taxonomy_version_id not in (None, self.classifier.taxonomy_version_id):
            raise ValueError("Classification run belongs to another taxonomy version")
        run.taxonomy_version_id = self.classifier.taxonomy_version_id
        # Failure rollback must not erase the run's immutable taxonomy context.
        self.session.commit()
        # 1. Query candidate units with optional official answer text
        query = (
            select(Unit, Document, UnitAnswer.answer_text)
            .join(Document, Unit.document_id == Document.id)
            .join(DocType, DocType.id == Document.doc_type_id)
            .join(Paper, Paper.id == func.coalesce(Unit.extraction_data['paper_id'].astext,Document.paper_id))
            .outerjoin(UnitAnswer, Unit.id == UnitAnswer.unit_id)
            .where(
                Unit.current.is_(True),
                Document.superseded.is_(False),
                Unit.is_gradable.is_(True),
                Document.catalog_status == "confirmed",
                or_(Document.current_revision_id.is_not(None),Document.extract_status.in_(["ok", "ok_with_warnings"])),
                Document.course_level == "final",
                Document.provenance_status == "verified",
                Document.scheme_id == "s2023",
                Paper.scheme_id == Document.scheme_id,
                Paper.is_current.is_(True),
                DocType.has_questions.is_(True),
            )
        )

        if resume:
            query = query.where(Unit.classify_status.not_in(["skipped", "excluded"]))
        else:
            query = query.where(Unit.classify_status.not_in(["skipped", "excluded"]))

        if doc_id is not None:
            query = query.where(Document.id == doc_id)
        if paper_id is not None:
            query = query.where(func.coalesce(Unit.extraction_data['paper_id'].astext,Document.paper_id) == paper_id)
        if resume:
            query = query.where(~select(TagSuggestion.id).where(
                TagSuggestion.unit_id == Unit.id,
                TagSuggestion.taxonomy_version_id == self.classifier.taxonomy_version_id,
                TagSuggestion.is_shadow == is_shadow,
            ).exists())
            # A reviewed gap is work for the taxonomy queue. Do not repeatedly
            # retry it ahead of later questions on each resumable run. Another
            # taxonomy version, a resolved gap or --no-resume can retry it.
            open_gap = select(TaxonomyGap.id).join(Run, Run.id == TaxonomyGap.run_id).where(
                TaxonomyGap.unit_id == Unit.id, TaxonomyGap.status == "open",
                Run.taxonomy_version_id == self.classifier.taxonomy_version_id,
            ).exists()
            query = query.where(~open_gap)

        query = query.order_by(Document.attempt_id.desc(), Unit.id.asc()).limit(limit)
        results = self.session.execute(query).all()

        bucket_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_primary = 0
        total_secondary = 0
        processed_count = 0
        quota_hit = False
        failed_count = 0

        for unit, doc, answer_text in results:
            try:
                if doc.current_revision_id is not None:
                    from caf_db.models.extraction import ExtractionRevision
                    from caf_l2.revisions import extraction_ready, flatten_snapshots, complete_answer_text
                    revision = self.session.get(ExtractionRevision, doc.current_revision_id)
                    if revision is None or not extraction_ready(self.session, revision):
                        continue
                root = unit
                parents = []
                seen = {unit.id}
                while root.parent_unit_id is not None:
                    parent = self.session.get(Unit, root.parent_unit_id)
                    if parent is None or parent.document_id != doc.id or parent.id in seen:
                        raise ValueError("Invalid main-question ancestry")
                    seen.add(parent.id)
                    parents.append(parent.question_text)
                    root = parent
                if doc.current_revision_id is not None:
                    question = next((q for q in revision.questions if q['question_id'] == unit.stable_question_id), None)
                    if question is None:
                        raise ValueError('Current extraction has no complete root context for this part')
                    snapshot = next(n for n in revision.parsed_units if n['stable_question_id'] == unit.stable_question_id)
                    parents = ['\n'.join(n['question_text'] for n in flatten_snapshots([snapshot]))]
                    if not answer_text:
                        answer_text = complete_answer_text(question)
                # Classify (passes answer text if available)
                res: ClassificationResult = self.classifier.classify_unit(
                    paper_id=unit.extraction_data.get('paper_id') or doc.paper_id or "",
                    question_text=unit.question_text,
                    context_text="\n".join(reversed(parents)),
                    answer_text=answer_text or "",
                    chapter_hint_id=doc.chapter_hint_node_id,
                    fingerprint=unit.fingerprint,
                    run_id=run_id,
                    use_llm=use_llm,
                )

                # Persist Primary Suggestion
                prim_sugg = TagSuggestion(
                    model_id=res.evidence.get("model_id"),
                    prompt_version="textbook-v1" if res.method == "llm" else None,
                    taxonomy_version_id=self.classifier.taxonomy_version_id,
                    descriptor_revision_id=res.evidence["descriptor_revisions"][res.primary_node_id],
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
                        "source_document_id": doc.id,
                        "source_document_sha256": doc.sha256,
                        "main_question_id": root.id,
                        "part_label": unit.label_path,
                        "extraction_revision_id": doc.current_revision_id,
                        "stable_question_id": unit.stable_question_id,
                    },
                    is_shadow=is_shadow,
                )
                self.session.add(prim_sugg)
                total_primary += 1

                # Persist Secondary Suggestions
                for sec_node_id in res.secondary_node_ids:
                    sec_sugg = TagSuggestion(
                        model_id=res.evidence.get("model_id"),
                        prompt_version="textbook-v1" if res.method == "llm" else None,
                        taxonomy_version_id=self.classifier.taxonomy_version_id,
                        descriptor_revision_id=res.evidence["descriptor_revisions"][sec_node_id],
                        unit_id=unit.id,
                        run_id=run_id,
                        node_id=sec_node_id,
                        role="secondary",
                        method=res.method,
                        bucket=res.bucket,
                        evidence={**res.evidence, "primary_ref": res.primary_node_id,
                                  "source_document_id": doc.id,
                                  "source_document_sha256": doc.sha256,
                                  "main_question_id": root.id, "part_label": unit.label_path},
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

            except NeedsTaxonomyReview as gap:
                self.session.add(TaxonomyGap(unit_id=unit.id, run_id=run_id,
                                            note=str(gap), status="open"))
                if not is_shadow:
                    unit.classify_status = "needs_review"
                bucket_counts["D"] += 1
                processed_count += 1
                self.session.commit()

            except QuotaExhaustedError as q_err:
                logger.warning("Quota exhausted on unit ID %s: %s", unit.id, q_err)
                quota_hit = True
                self.session.rollback()
                break

            except Exception as e:
                logger.error("Error classifying unit ID %s: %s", unit.id, e)
                self.session.rollback()
                unit.classify_status = "failed"
                self.session.commit()
                failed_count += 1
                continue

        status_msg = "Completed successfully."
        if quota_hit:
            status_msg = (
                f"Google Gemini daily quota / rate limit reached. "
                f"Successfully saved {processed_count} units before stopping. "
                f"Re-run with '--resume' once your quota resets to continue seamlessly."
            )
        elif failed_count:
            status_msg = f"Saved {processed_count} units; {failed_count} units failed and need retry. Inspect classification errors before resuming."

        return ClassificationSummary(
            total_processed=processed_count,
            buckets=bucket_counts,
            primary_suggestions=total_primary,
            secondary_suggestions=total_secondary,
            is_partial=quota_hit or failed_count > 0,
            quota_exhausted=quota_hit,
            failed_units=failed_count,
            status_message=status_msg,
        )
