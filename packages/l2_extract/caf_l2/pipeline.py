"""L2 Extraction pipeline orchestrator."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pymupdf as fitz
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from caf_common.blob_store import BlobStore
from caf_db.models.ingest import Document, Unit, UnitAnswer
from caf_l2.blocks import build_block_stream
from caf_l2.overrides import apply_override, load_override
from caf_l2.pairing import flatten_units, pair_answers
from caf_l2.preflight import preflight_check
from caf_l2.profiles import ExtractionProfile, load_profile, resolve_profile
from caf_l2.render import render_debug_html
from caf_l2.segmenter import ParsedUnit, Segmenter
from caf_l2.validators import DocumentValidator, ValidationResult


@dataclass
class ExtractionSummary:
    document_id: int
    sha256: str
    extract_status: str
    page_count: int
    has_text_layer: bool
    total_units: int
    gradable_units: int
    validation_issues: list[dict[str, str]]
    debug_html_path: str | None = None


class ExtractionPipeline:
    """End-to-end extraction pipeline from document blob to database units."""

    def __init__(
        self,
        blob_store: BlobStore,
        profiles_dir: Path,
        overrides_dir: Path,
        debug_dir: Path | None = None,
    ):
        self.blob_store = blob_store
        self.profiles_dir = profiles_dir
        self.overrides_dir = overrides_dir
        self.debug_dir = debug_dir

    def extract_document(
        self,
        session: Session,
        document_id: int,
        run_id: int,
        profile_override_path: Path | None = None,
    ) -> ExtractionSummary:
        """Run extraction pipeline on a confirmed document."""
        doc = session.get(Document, document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Mark document as running
        doc.extract_status = "running"
        session.commit()

        try:
            # 1. Read PDF blob
            pdf_bytes = self.blob_store.read(doc.sha256)
            fitz_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            # 2. Preflight
            preflight = preflight_check(fitz_doc)
            doc.page_count = preflight.page_count
            doc.has_text_layer = preflight.has_text_layer

            # 3. Block stream & Cleaning
            lines = build_block_stream(fitz_doc)

            # 4. Resolve profile
            if profile_override_path and profile_override_path.is_file():
                profile = load_profile(profile_override_path)
            else:
                profile = resolve_profile(
                    self.profiles_dir,
                    scheme_id=doc.scheme_id or "s2023",
                    doc_type_id=doc.doc_type_id or "suggested_answer",
                    paper_id=doc.paper_id,
                )

            # 5. Segment
            segmenter = Segmenter(profile=profile, doc_sha256=doc.sha256)
            root_units = segmenter.segment(lines)

            # 6. Pairing
            answers = pair_answers(
                root_units,
                mode=profile.mode,
                key_patterns=profile.patterns,
            )

            # 7. Check and apply manual overrides
            override_data = load_override(self.overrides_dir, doc.sha256)
            if override_data:
                root_units = apply_override(root_units, override_data)
                # Re-pair answers if needed
                answers = pair_answers(
                    root_units,
                    mode=profile.mode,
                    key_patterns=profile.patterns,
                )

            # 8. Validate
            validator = DocumentValidator(
                profile=profile,
                has_answers=True,
                optional_pick=segmenter.optional_pick,
            )
            validation = validator.validate(root_units, answers)

            # 9. Debug render if requested or debug_dir set
            debug_html_path: str | None = None
            if self.debug_dir:
                out_path = render_debug_html(
                    doc.sha256, lines, root_units, validation, self.debug_dir
                )
                debug_html_path = str(out_path)

            # 10. Persist to DB
            self._persist_units(
                session=session,
                doc=doc,
                run_id=run_id,
                root_units=root_units,
                answers=answers,
                validation=validation,
            )

            all_units = flatten_units(root_units)
            gradables = [u for u in all_units if u.is_gradable]

            return ExtractionSummary(
                document_id=doc.id,
                sha256=doc.sha256,
                extract_status=validation.outcome,
                page_count=preflight.page_count,
                has_text_layer=preflight.has_text_layer,
                total_units=len(all_units),
                gradable_units=len(gradables),
                validation_issues=[
                    {"code": i.code, "severity": i.severity, "message": i.message}
                    for i in validation.issues
                ],
                debug_html_path=debug_html_path,
            )

        except Exception as e:
            session.rollback()
            # Update doc to failed
            with session.begin_nested():
                d_fail = session.get(Document, document_id)
                if d_fail:
                    d_fail.extract_status = "failed"
            session.commit()
            raise e

    def _persist_units(
        self,
        session: Session,
        doc: Document,
        run_id: int,
        root_units: list[ParsedUnit],
        answers: dict[str, Any],
        validation: ValidationResult,
    ) -> None:
        """Persist extracted units and answers transactionally."""
        # 1. Mark existing units for this document as current = False
        session.execute(
            update(Unit)
            .where(Unit.document_id == doc.id, Unit.current.is_(True))
            .values(current=False)
        )

        # 2. Insert units hierarchically
        all_units = flatten_units(root_units)
        db_units: dict[str, Unit] = {}

        # Queue-based breadth-first insertion to satisfy foreign key self-references
        queue: list[ParsedUnit] = list(root_units)
        while queue:
            curr = queue.pop(0)
            parent_db_id = (
                db_units[curr.parent_label_path].id
                if curr.parent_label_path and curr.parent_label_path in db_units
                else None
            )

            db_u = Unit(
                document_id=doc.id,
                extract_run_id=run_id,
                parent_unit_id=parent_db_id,
                label_path=curr.label_path,
                display_label=curr.display_label,
                kind=curr.kind,
                is_gradable=curr.is_gradable,
                marks=curr.marks,
                marks_source=curr.marks_source,
                choice_role=curr.choice_role,
                or_group=curr.or_group,
                page_start=curr.page_start,
                page_end=curr.page_end,
                block_start=curr.block_start,
                block_end=curr.block_end,
                question_text=curr.question_text,
                text_origin="pdf",
                fingerprint=curr.fingerprint,
                parse_confidence=curr.parse_confidence,
                validation_flags=curr.validation_flags,
                classify_status="pending",
                current=True,
            )
            session.add(db_u)
            session.flush()  # Populates db_u.id
            db_units[curr.label_path] = db_u

            # Add answers if present
            ans = answers.get(curr.label_path)
            if ans and (ans.answer_text or ans.mcq_correct_option):
                db_ans = UnitAnswer(
                    unit_id=db_u.id,
                    answer_document_id=doc.id,
                    answer_text=ans.answer_text,
                    page_start=ans.page_start,
                    page_end=ans.page_end,
                    mcq_correct_option=ans.mcq_correct_option,
                    pairing_method=ans.pairing_method,
                )
                session.add(db_ans)

            # Append children to queue
            queue.extend(curr.children)

        # 3. Update document status
        doc.extract_status = validation.outcome
        doc.extract_run_id = run_id
        session.commit()
