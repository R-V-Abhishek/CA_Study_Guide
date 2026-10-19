"""L4 Curation publish engine: decisions, appearances, and tags."""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.ref import DocType, LawBoundary


class StaleDecisionError(ValueError):
    """The suggestion was already reviewed by another request."""


def compute_law_stale(
    session: Session, attempt_id: str, paper_id: str, node_ids: list[str]
) -> bool:
    """Check if exam appearance is stale per ref.law_boundary."""
    paper_code = paper_id.split(".")[-1]
    boundaries = (
        session.query(LawBoundary)
        .filter(LawBoundary.paper_code == paper_code)
        .all()
    )
    for b in boundaries:
        if b.policy == "mark_stale" and b.first_applicable_attempt:
            if attempt_id < b.first_applicable_attempt:
                return True
    return False


def make_decision(
    session: Session,
    unit_id: int,
    action: str,  # accept | accept_alt | edit | none_fits | exclude | bulk_accept | undo
    payload: dict[str, Any],
    suggestion_run_id: int | None = None,
    seconds_spent: float | None = None,
    blind: bool = False,
    actor_id: int | None = None,
    require_pending: bool = False,
) -> Decision:
    """Record curator decision and publish appearance to core.* atomically."""
    unit = session.scalars(
        select(Unit).where(Unit.id == unit_id).with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if not unit:
        raise ValueError(f"Unit {unit_id} not found")

    if require_pending and (not unit.current or unit.classify_status != "suggested"):
        raise StaleDecisionError("This suggestion has already been reviewed or superseded; refresh the queue.")

    doc = session.get(Document, unit.document_id)
    if not doc:
        raise ValueError(f"Document {unit.document_id} not found")
    if action not in ("none_fits", "exclude"):
        from caf_db.models.taxonomy import TaxonomyMember, TaxonomyRelease
        selected_ids = [payload.get("primary_node_id"), *payload.get("secondary_node_ids", [])]
        rebuilt = session.scalar(select(TaxonomyMember.node_id).join(TaxonomyRelease,
            TaxonomyRelease.taxonomy_version_id == TaxonomyMember.taxonomy_version_id
        ).where(TaxonomyMember.node_id.in_(selected_ids), TaxonomyRelease.status != "legacy").limit(1))
        if rebuilt:
            raise ValueError("Textbook labels require a complete root classification review with expected suggestion and publication revisions; use the revisioned classification review operation")

    # 1. Record Decision
    decision = Decision(
        unit_fingerprint=unit.fingerprint,
        actor_id=actor_id,
        action=action,
        payload=payload,
        suggestion_run_id=suggestion_run_id,
        blind=blind,
        seconds_spent=seconds_spent,
    )
    session.add(decision)
    session.flush()

    # 2. Exclude / None-fits actions do not publish appearances
    if action in ("none_fits", "exclude"):
        unit.classify_status = "excluded" if action == "exclude" else "failed"
        session.commit()
        return decision

    # 3. Publish Appearance
    primary_node_id = payload.get("primary_node_id")
    if not primary_node_id:
        raise ValueError("Missing primary_node_id in publication payload")

    secondary_node_ids = payload.get("secondary_node_ids", [])
    all_nodes = [primary_node_id] + list(secondary_node_ids)

    # Normalize shares (primary = 1.0, secondary = 0.5)
    total_weight = 1.0 + (0.5 * len(secondary_node_ids))
    primary_share = round(1.0 / total_weight, 4)
    secondary_share = round(0.5 / total_weight, 4) if secondary_node_ids else 0.0

    law_stale = compute_law_stale(
        session, doc.attempt_id or "2024-05", doc.paper_id or "s2023.P1", all_nodes
    )

    doc_type = session.get(DocType, doc.doc_type_id) if doc.doc_type_id else None
    signal_class = doc_type.signal_class if doc_type else "exam"

    # Upsert core.appearance
    existing_app = (
        session.query(Appearance)
        .filter(Appearance.unit_fingerprint == unit.fingerprint)
        .first()
    )

    gist_text = payload.get("gist") or unit.display_label

    if not existing_app:
        app = Appearance(
            unit_fingerprint=unit.fingerprint,
            source_unit_id=unit.id,
            doc_sha256=doc.sha256,
            attempt_id=doc.attempt_id or "2024-05",
            source_paper_id=doc.paper_id or "s2023.P1",
            doc_type_id=doc.doc_type_id or "suggested_answer",
            signal_class=signal_class,
            series=doc.series,
            display_label=unit.display_label,
            marks=unit.marks,
            gist=gist_text,
            page_start=unit.page_start,
            page_end=unit.page_end,
            law_stale=law_stale,
            status="published",
        )
        session.add(app)
        session.flush()
        app_id = app.id
    else:
        existing_app.source_unit_id = unit.id
        existing_app.marks = unit.marks
        existing_app.gist = gist_text
        existing_app.display_label = unit.display_label
        existing_app.page_start = unit.page_start
        existing_app.page_end = unit.page_end
        existing_app.law_stale = law_stale
        existing_app.status = "published"
        app_id = existing_app.id

    # 4. Replace appearance tags
    session.execute(
        delete(AppearanceTag).where(AppearanceTag.appearance_id == app_id)
    )

    # Insert primary tag
    session.add(
        AppearanceTag(
            appearance_id=app_id,
            node_id=primary_node_id,
            role="primary",
            share=primary_share,
            decision_id=decision.id,
        )
    )

    # Insert secondary tags
    for sec_id in secondary_node_ids:
        session.add(
            AppearanceTag(
                appearance_id=app_id,
                node_id=sec_id,
                role="secondary",
                share=secondary_share,
                decision_id=decision.id,
            )
        )

    # 5. Update unit status
    unit.classify_status = "decided"

    # 6. Change log
    session.add(
        ChangeLog(
            entity="appearance",
            entity_id=str(app_id),
            change="publish",
            after={
                "fingerprint": unit.fingerprint,
                "primary": primary_node_id,
                "secondaries": secondary_node_ids,
            },
        )
    )

    session.commit()
    return decision


def bulk_accept_bucket_a(session: Session, document_id: int, actor_id: int | None = None) -> int:
    """Retain the historical entry point without automatic model-score publication."""
    raise ValueError("Automatic bucket publication is disabled; an authenticated administrator must review explicit root revisions in the bulk review workspace")
