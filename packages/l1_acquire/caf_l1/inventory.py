"""Turn the Phase 3 source inventory into an explicit, bounded acquisition queue."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from caf_db.models.ingest import DiscoveredLink


@dataclass(frozen=True)
class AcquisitionItem:
    inventory_id: str
    url: str | None
    outcome: str
    reason: str | None
    metadata: dict[str, Any]


def plan_inventory(path: Path, *, limit: int = 50, paper_id: str | None = None,
                   attempt_id: str | None = None, include_older: bool = False,
                   course_level: str | None = None) -> list[AcquisitionItem]:
    if limit < 1:
        raise ValueError("limit must be positive")
    records = json.loads(path.read_text())["records"]
    items = []
    for record in records:
        if course_level and record["course_level"].lower() != course_level.lower():
            continue
        if paper_id and paper_id not in [record["paper_id"], *record["paper_ids"]]:
            continue
        if attempt_id and record["attempt_id"] != attempt_id:
            continue
        level = record["course_level"].lower()
        attempt = record["attempt_id"]
        metadata = {key: record.get(key) for key in ("scheme_id", "attempt_id", "paper_id", "paper_ids",
                       "doc_type_id", "series", "title", "source_family", "collection_id", "paper_page_ranges")}
        metadata.update(course_level=level if level in {"foundation", "intermediate", "final"} else None,
                        catalog_status="needs_curation", inventory_id=record["id"],
                        landing_url=record["landing_url"], artifact_role=record["artifact_role"],
                        role_review_status=record.get("role_review_status"))
        if record["source_family"] in {"model", "case_study", "ibs", "case_collection"}:
            metadata["collection_id"] = record.get("collection_id") or record.get("title")
        outcome, reason = "pending", None
        if level in {"foundation", "intermediate"}:
            outcome, reason = "outside_corpus", "Course is outside Final scope"
        elif level != "final":
            outcome, reason = "needs_review", "Course identity unresolved in official navigation"
        elif record["artifact_role"] == "announcement" or not record["doc_type_id"]:
            outcome, reason = "not_question_artifact", "Announcement or document role unresolved"
        elif not include_older and (record["scheme_id"] != "s2023" or (attempt and attempt < "2024-05")):
            outcome, reason = "older_inventory", "Outside initial current-scheme scope"
        elif not record["download_url"]:
            outcome, reason = "source_gap", "No available download URL"
        elif not attempt and record["source_family"] not in {"model", "case_study", "ibs", "case_collection"}:
            outcome, reason = "needs_review", "Attempt required for source family"
        items.append(AcquisitionItem(record["id"], record["download_url"], outcome, reason, metadata))
        if len(items) == limit:
            break
    return items


def enqueue_inventory(items: list[AcquisitionItem], session) -> int:
    created = 0
    for item in items:
        if item.outcome != "pending":
            continue
        existing = session.execute(sa.select(DiscoveredLink).where(DiscoveredLink.url == item.url)).scalar_one_or_none()
        if existing is None:
            session.add(DiscoveredLink(url=item.url, anchor_text=item.metadata.get("title"),
                                       inferred={**item.metadata, "inventory_associations": [item.inventory_id]}, link_status="new"))
            created += 1
        else:
            metadata = dict(existing.inferred or {})
            associations = list(metadata.get("inventory_associations", []))
            if item.inventory_id not in associations:
                associations.append(item.inventory_id)
            existing.inferred = {**metadata, "inventory_associations": associations}
    session.commit()
    return created
