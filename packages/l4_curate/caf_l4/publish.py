"""L4 Curation publish engine: decisions, appearances, and tags."""

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_db.models.ref import DocType, LawBoundary


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
) -> Decision:
    """Record curator decision and publish appearance to core.* atomically."""
    unit = session.get(Unit, unit_id)
    if not unit:
        raise ValueError(f"Unit {unit_id} not found")

    doc = session.get(Document, unit.document_id)
    if not doc:
        raise ValueError(f"Document {unit.document_id} not found")

    # 1. Record Decision
    decision = Decision(
        unit_fingerprint=unit.fingerprint,
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


def bulk_accept_bucket_a(session: Session, document_id: int) -> int:
    """Bulk accept all remaining Bucket A suggestions for a confirmed document."""
    doc = session.get(Document, document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    # Find pending units with Bucket A primary suggestions
    units = (
        session.query(Unit)
        .filter(
            Unit.document_id == document_id,
            Unit.current.is_(True),
            Unit.classify_status == "suggested",
        )
        .all()
    )

    accepted_count = 0
    for u in units:
        # Check suggestions
        suggestions = (
            session.query(TagSuggestion)
            .filter(
                TagSuggestion.unit_id == u.id,
                TagSuggestion.is_shadow.is_(False),
            )
            .all()
        )
        primary_sugg = next(
            (s for s in suggestions if s.role == "primary" and s.bucket == "A"),
            None,
        )
        if not primary_sugg:
            continue

        secondary_ids = [
            s.node_id for s in suggestions if s.role == "secondary"
        ]
        gist = (
            primary_sugg.evidence.get("gist")
            if isinstance(primary_sugg.evidence, dict)
            else None
        )

        make_decision(
            session=session,
            unit_id=u.id,
            action="bulk_accept",
            payload={
                "primary_node_id": primary_sugg.node_id,
                "secondary_node_ids": secondary_ids,
                "gist": gist or u.display_label,
            },
            suggestion_run_id=primary_sugg.run_id,
        )
        accepted_count += 1

    return accepted_count
