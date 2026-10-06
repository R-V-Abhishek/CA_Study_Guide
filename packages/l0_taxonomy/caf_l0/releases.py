"""Dry-run-first import and activation of independently sourced taxonomy releases.

No draft review flags constitute authenticated approvals. Membership and descriptor
history are append-only; activation never mutates the legacy hierarchy or labels.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import sqlalchemy as sa
from sqlalchemy.orm import Session
from caf_contracts.taxonomy import DescriptorContent
from caf_db.models.ref import Node, TaxonomyVersion
from caf_db.models.taxonomy import (TaxonomyRelease, TaxonomyMember, TextbookArtifact,
    NodeSourceSpan, DescriptorRevision, DescriptorApproval, TaxonomyCrosswalk, ProgressMigration)
from caf_db.models.app import Progress, Note, UserAccount


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def active_version(session: Session) -> TaxonomyRelease | None:
    return session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.status == "active"))


def get_release(session: Session, version_id: str) -> TaxonomyRelease:
    release = session.get(TaxonomyRelease, version_id)
    if release is None:
        raise ValueError("Unknown taxonomy release")
    return release


def version_nodes(session: Session, taxonomy_version_id: int, paper_id: str | None = None):
    query = sa.select(TaxonomyMember).where(TaxonomyMember.taxonomy_version_id == taxonomy_version_id)
    if paper_id:
        query = query.where(TaxonomyMember.paper_id == paper_id)
    return list(session.scalars(query.order_by(TaxonomyMember.paper_id, TaxonomyMember.seq, TaxonomyMember.node_id)))


def latest_descriptor(session: Session, taxonomy_version_id: int, node_id: str):
    return session.scalar(sa.select(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == taxonomy_version_id, DescriptorRevision.node_id == node_id).order_by(DescriptorRevision.revision.desc()).limit(1))


def descriptor_approved(session: Session, revision: DescriptorRevision | None) -> bool:
    if revision is None:
        return False
    approval = session.get(DescriptorApproval, revision.id)
    return approval is not None and approval.content_hash == revision.content_hash


def span_context(span: NodeSourceSpan, artifact: TextbookArtifact) -> dict:
    # Heading inventories belong in the administrator source endpoint. Repeating
    # them in every conceptual node makes a full textbook tree unnecessarily large.
    fields = ("applicable_attempts", "download_url", "landing_url", "fallback",
              "target_applicability", "instrument", "source_context", "sha256",
              "retrieved_at", "page_count", "edition_evidence", "reprint",
              "applicability_basis", "publication_date_status")
    return {**{key: artifact.metadata_json[key] for key in fields if key in artifact.metadata_json},
        "artifact_id": artifact.id, "edition": artifact.edition, "availability": artifact.availability,
        "pdf_page_start": span.pdf_page_start, "pdf_page_end": span.pdf_page_end,
        "review_status": span.review_status}


def source_context(session: Session, taxonomy_version_id: int, node_id: str) -> list[dict]:
    rows = session.execute(sa.select(NodeSourceSpan, TextbookArtifact).join(TextbookArtifact).where(NodeSourceSpan.taxonomy_version_id == taxonomy_version_id, NodeSourceSpan.node_id == node_id)).all()
    return [span_context(span, artifact) for span, artifact in rows]


def source_contexts(session: Session, taxonomy_version_id: int) -> dict[str, list[dict]]:
    contexts = {}
    for span, artifact in session.execute(sa.select(NodeSourceSpan, TextbookArtifact).join(TextbookArtifact).where(NodeSourceSpan.taxonomy_version_id == taxonomy_version_id)):
        contexts.setdefault(span.node_id, []).append(span_context(span, artifact))
    return contexts


def eligible_candidates(session: Session, taxonomy_version_id: int, paper_id: str | None = None) -> list[TaxonomyMember]:
    members = version_nodes(session, taxonomy_version_id, paper_id)
    by_id = {n.node_id: n for n in members}
    containers = {n.parent_id for n in members if n.parent_id is not None}
    revisions = list(session.scalars(sa.select(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == taxonomy_version_id).order_by(DescriptorRevision.revision)))
    latest = {r.node_id: r for r in revisions}
    approved = {a.revision_id: a.content_hash for a in session.scalars(sa.select(DescriptorApproval).join(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == taxonomy_version_id))}
    sources = {}
    for span, artifact in session.execute(sa.select(NodeSourceSpan, TextbookArtifact).join(TextbookArtifact).where(NodeSourceSpan.taxonomy_version_id == taxonomy_version_id)):
        sources.setdefault(span.node_id, []).append((span, artifact))
    result = []
    for node in members:
        if node.level != "subtopic" or node.node_id in containers:
            continue
        descriptor = latest.get(node.node_id)
        if descriptor is None or approved.get(descriptor.id) != descriptor.content_hash:
            continue
        current = node
        supported = True
        while current:
            spans = sources.get(current.node_id, [])
            if not spans or any(span.review_status != "reviewed" or artifact.availability != "verified" for span, artifact in spans):
                supported = False
                break
            current = by_id.get(current.parent_id)
        if supported:
            result.append(node)
    return result


def validate_manifest(manifest: dict, legacy_ids: set[str] | None = None) -> dict:
    for key in ("version_id", "target_attempt", "papers", "textbook_artifacts", "nodes", "descriptors"):
        if key not in manifest:
            raise ValueError(f"Manifest requires {key}")
    if manifest["version_id"] == "legacy":
        raise ValueError("Legacy release identity is reserved")
    if manifest["target_attempt"] != "2027-05":
        raise ValueError("Phase 3 target must remain May 2027")
    nodes = {n["id"]: n for n in manifest["nodes"]}
    artifacts = {a["id"]: a for a in manifest["textbook_artifacts"]}
    if len(nodes) != len(manifest["nodes"]) or len(artifacts) != len(manifest["textbook_artifacts"]):
        raise ValueError("Duplicate node or artifact IDs")
    if legacy_ids and legacy_ids.intersection(nodes):
        raise ValueError("New taxonomy cannot reuse legacy node IDs")
    for node in nodes.values():
        kind = node.get("kind", node.get("level"))
        if kind not in {"module", "chapter", "unit", "topic", "subtopic"}:
            raise ValueError("Invalid hierarchy level")
        seen = {node["id"]}
        parent = node.get("parent_id")
        while parent is not None:
            if parent in seen:
                raise ValueError("Taxonomy cycle")
            seen.add(parent)
            if parent not in nodes or nodes[parent]["paper_id"] != node["paper_id"]:
                raise ValueError("Missing or cross-paper parent")
            parent = nodes[parent].get("parent_id")
        if not node.get("source_spans"):
            raise ValueError("Every conceptual node requires textbook evidence")
        for span in node["source_spans"]:
            artifact = artifacts.get(span["artifact_id"])
            if artifact is None or artifact["paper_id"] != node["paper_id"]:
                raise ValueError("Source span artifact/paper mismatch")
            if span["pdf_page_start"] < 1 or span["pdf_page_end"] < span["pdf_page_start"]:
                raise ValueError("Invalid textbook page span")
            if artifact.get("page_count") and span["pdf_page_end"] > artifact["page_count"]:
                raise ValueError("Textbook page span exceeds artifact")
    for artifact in artifacts.values():
        if artifact["course_level"] != "Final":
            raise ValueError("Textbook taxonomy requires Final-level sources")
        applicable = artifact.get("applicable_attempts", [])
        if "2027-05" not in applicable and "2026-01" not in applicable:
            if artifact.get("availability") == "verified":
                raise ValueError("Verified section requires May 2027 or January 2026 applicability")
        if artifact.get("availability") == "verified" and (not artifact.get("sha256") or not artifact.get("edition_evidence")):
            raise ValueError("Verified textbooks require hash and edition evidence")
        if artifact.get("availability") == "verified":
            path = Path(artifact.get("local_path", ""))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("Verified textbook bytes do not match artifact hash")
            import fitz
            with fitz.open(path) as pdf:
                if pdf.page_count != artifact.get("page_count"):
                    raise ValueError("Verified textbook page count mismatch")
    descriptor_ids = set()
    for descriptor in manifest["descriptors"]:
        node_id = descriptor["node_id"]
        if node_id in descriptor_ids or node_id not in nodes or nodes[node_id].get("kind", nodes[node_id].get("level")) != "subtopic":
            raise ValueError("Invalid or duplicate descriptor node")
        descriptor_ids.add(node_id)
        validated = DescriptorContent.model_validate({k: descriptor[k] for k in DescriptorContent.model_fields if k in descriptor})
        for citation in validated.source_spans:
            if not any(citation.artifact_id == span["artifact_id"] and citation.pdf_page_start >= span["pdf_page_start"] and citation.pdf_page_end <= span["pdf_page_end"] for span in nodes[node_id]["source_spans"]):
                raise ValueError("Descriptor citation outside node textbook evidence")
    for mapping in manifest.get("crosswalk", []):
        if mapping["relation"] not in {"exact", "split", "merge", "unresolved", "deprecated"}:
            raise ValueError("Unknown legacy mapping relation")
        if mapping.get("new_node_id") is not None and mapping["new_node_id"] not in nodes:
            raise ValueError("Legacy mapping target outside release")
    return {"manifest_hash": digest(manifest), "node_count": len(nodes), "source_count": len(artifacts), "descriptor_count": len(descriptor_ids), "dry_run": True}


def import_release(session: Session, manifest: dict, *, dry_run: bool = True) -> dict:
    existing = session.get(TaxonomyRelease, manifest["version_id"])
    if existing:
        if existing.manifest_hash != digest(manifest):
            raise ValueError("Release identity already bound to a different manifest")
        return release_report(session, existing.version_id)
    textbook_ids = set(session.scalars(sa.select(TaxonomyMember.node_id).join(
        TaxonomyRelease, TaxonomyRelease.taxonomy_version_id == TaxonomyMember.taxonomy_version_id
    ).where(TaxonomyRelease.status != "legacy")))
    legacy_snapshot_ids = set(session.scalars(sa.select(TaxonomyMember.node_id).join(
        TaxonomyRelease, TaxonomyRelease.taxonomy_version_id == TaxonomyMember.taxonomy_version_id
    ).where(TaxonomyRelease.status == "legacy")))
    legacy_ids = (set(session.scalars(sa.select(Node.id))) - textbook_ids) | legacy_snapshot_ids
    report = validate_manifest(manifest, legacy_ids)
    existing_nodes = {n.id: n for n in session.scalars(sa.select(Node).where(
        Node.id.in_([node["id"] for node in manifest["nodes"]])
    ))}
    for node in manifest["nodes"]:
        previous = existing_nodes.get(node["id"])
        if previous is None:
            continue
        fields = (node["paper_id"], node.get("parent_id"), node.get("kind", node.get("level")),
                  node["name"], node.get("ordinal", node.get("seq", 0)))
        if fields != (previous.paper_id, previous.parent_id, previous.level, previous.name, previous.seq):
            raise ValueError("Existing textbook node ID has incompatible immutable structural fields; allocate a new ID")
    if dry_run:
        return report
    version = TaxonomyVersion(yaml_hash=report["manifest_hash"], notes=f"Textbook draft {manifest['version_id']}")
    session.add(version)
    session.flush()
    release = TaxonomyRelease(version_id=manifest["version_id"], taxonomy_version_id=version.id, target_attempt=manifest["target_attempt"], status="draft", manifest_hash=report["manifest_hash"], manifest=manifest)
    session.add(release)
    for artifact in manifest["textbook_artifacts"]:
        session.add(TextbookArtifact(id=artifact["id"], taxonomy_version_id=version.id, paper_id=artifact["paper_id"], course_level=artifact["course_level"], edition=artifact["edition"], availability=artifact["availability"], sha256=artifact.get("sha256"), page_count=artifact.get("page_count"), metadata_json=artifact))
    pending = list(manifest["nodes"])
    inserted = set()
    while pending:
        for node in pending[:]:
            if node.get("parent_id") is not None and node["parent_id"] not in inserted:
                continue
            fields = dict(paper_id=node["paper_id"], parent_id=node.get("parent_id"), level=node.get("kind", node.get("level")), name=node["name"], seq=node.get("ordinal", node.get("seq", 0)))
            if node["id"] not in existing_nodes:
                session.add(Node(id=node["id"], **fields, status="active", created_in=version.id, updated_in=version.id))
                session.flush()
            session.add(TaxonomyMember(taxonomy_version_id=version.id, node_id=node["id"], **fields, heading_origin=node.get("heading_origin", "official")))
            session.flush()
            for span in node["source_spans"]:
                session.add(NodeSourceSpan(taxonomy_version_id=version.id, node_id=node["id"], artifact_id=span["artifact_id"], pdf_page_start=span["pdf_page_start"], pdf_page_end=span["pdf_page_end"], review_status="pending"))
            inserted.add(node["id"])
            pending.remove(node)
    for descriptor in manifest["descriptors"]:
        content = DescriptorContent.model_validate({k: descriptor[k] for k in DescriptorContent.model_fields if k in descriptor}).model_dump()
        session.add(DescriptorRevision(taxonomy_version_id=version.id, node_id=descriptor["node_id"], revision=1, content=content, content_hash=digest(content)))
    for mapping in manifest.get("crosswalk", []):
        # Preserve structured inventory evidence in the existing text contract.
        evidence = json.dumps(mapping["evidence"], ensure_ascii=False, sort_keys=True)
        session.add(TaxonomyCrosswalk(taxonomy_version_id=version.id, old_node_id=mapping["old_node_id"], new_node_id=mapping.get("new_node_id"), relation=mapping["relation"], evidence=evidence))
    session.flush()
    return release_report(session, release.version_id)


def require_administrator(session: Session, actor_id: int):
    actor = session.execute(sa.select(UserAccount.role, UserAccount.status).where(UserAccount.id == actor_id)).first()
    if actor is None or actor.role != "administrator" or actor.status != "active":
        raise ValueError("Active administrator approval required")


def revise_descriptor(session: Session, version_id: str, node_id: str, content: dict, actor_id: int):
    session.execute(sa.text("SELECT pg_advisory_xact_lock(731306)"))
    session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"descriptor:{version_id}:{node_id}"})
    release = get_release(session, version_id)
    node = session.get(TaxonomyMember, (release.taxonomy_version_id, node_id))
    if node is None or node.level != "subtopic":
        raise ValueError("Descriptor requires subtopic in specified version")
    actor = session.execute(sa.select(UserAccount.status).where(UserAccount.id == actor_id)).first()
    if actor is None or actor.status != "active":
        raise ValueError("Authenticated active reviewer required")
    validated = DescriptorContent.model_validate(content).model_dump()
    known_sources = source_context(session, release.taxonomy_version_id, node_id)
    for citation in validated["source_spans"]:
        if not any(citation["artifact_id"] == source["artifact_id"] and citation["pdf_page_start"] >= source["pdf_page_start"] and citation["pdf_page_end"] <= source["pdf_page_end"] for source in known_sources):
            raise ValueError("Descriptor citation must lie within node textbook source span")
    old = latest_descriptor(session, release.taxonomy_version_id, node_id)
    revision = DescriptorRevision(taxonomy_version_id=release.taxonomy_version_id, node_id=node_id, revision=old.revision + 1 if old else 1, content=validated, content_hash=digest(validated), created_by=actor_id)
    session.add(revision)
    session.flush()
    # Structural approval was for a concrete revision set; any edit invalidates it.
    session.expire(release)
    return revision


def approve_descriptor(session: Session, version_id: str, node_id: str, revision: int, actor_id: int):
    session.execute(sa.text("SELECT pg_advisory_xact_lock(731306)"))
    session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"descriptor:{version_id}:{node_id}"})
    release = get_release(session, version_id)
    actor = session.execute(sa.select(UserAccount.status).where(UserAccount.id == actor_id)).first()
    if actor is None or actor.status != "active":
        raise ValueError("Authenticated active reviewer required")
    latest = latest_descriptor(session, release.taxonomy_version_id, node_id)
    if latest is None or latest.revision != revision:
        raise ValueError("Descriptor revision changed; reload before approving")
    if latest.content.get("source_ambiguities"):
        raise ValueError("Resolve recorded textbook source issues before approving this descriptor")
    if not session.get(DescriptorApproval, latest.id):
        session.add(DescriptorApproval(revision_id=latest.id, approved_by=actor_id, content_hash=latest.content_hash))
        session.flush()
    return latest


def release_report(session: Session, version_id: str, *, include_personal_counts: bool = False) -> dict:
    release = get_release(session, version_id)
    nodes = version_nodes(session, release.taxonomy_version_id)
    sources = list(session.scalars(sa.select(TextbookArtifact).where(TextbookArtifact.taxonomy_version_id == release.taxonomy_version_id)))
    eligible = eligible_candidates(session, release.taxonomy_version_id)
    containers = {n.parent_id for n in nodes if n.parent_id is not None}
    subtopics = [n for n in nodes if n.level == "subtopic" and n.node_id not in containers]
    unresolved = [s.id for s in sources if s.availability != "verified"]
    missing_papers = sorted({f"s2023.P{i}" for i in range(1, 7)} - {s.paper_id for s in sources})
    revisions = list(session.scalars(sa.select(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id).order_by(DescriptorRevision.node_id, DescriptorRevision.revision)))
    latest = {r.node_id: r for r in revisions}
    approvals = {a.revision_id: a.content_hash for a in session.scalars(sa.select(DescriptorApproval).join(DescriptorRevision).where(DescriptorRevision.taxonomy_version_id == release.taxonomy_version_id))}
    unreviewed = [n.node_id for n in subtopics if n.node_id not in latest or approvals.get(latest[n.node_id].id) != latest[n.node_id].content_hash]
    contexts = source_contexts(session, release.taxonomy_version_id)
    unreviewed_sources = [n.node_id for n in nodes if not contexts.get(n.node_id) or
        any(s["review_status"] != "reviewed" or s["availability"] != "verified"
            for s in contexts[n.node_id])]
    blockers = []
    expected_ids = {n["id"] for n in release.manifest.get("nodes", [])}
    if release.status != "legacy" and expected_ids != {n.node_id for n in nodes}:
        blockers.append("Persisted hierarchy differs from the immutable manifest")
    if missing_papers: blockers.append("Missing paper selections: " + ", ".join(missing_papers))
    if unresolved: blockers.append("Unverified source artifacts")
    if unreviewed: blockers.append("Descriptors awaiting authenticated review")
    if unreviewed_sources: blockers.append("Source context awaiting review")
    if not subtopics: blockers.append("No classification subtopics")
    missing_subtopics = sorted({f"s2023.P{i}" for i in range(1, 7)} - {n.paper_id for n in subtopics})
    if missing_subtopics: blockers.append("Papers without classification coverage: " + ", ".join(missing_subtopics))
    # Explicit source gaps can never disappear behind a smaller extracted tree.
    if release.manifest.get("source_gaps") or release.manifest.get("unresolved_gaps"):
        blockers.append("Expected textbook structure has unresolved gaps")
    for gap in release.manifest.get("source_gaps", []):
        blockers.append(f"{gap['paper_id']}: {gap['reason']}")
    if any(gap.get("course_level") == "Final" for gap in release.manifest.get("question_inventory_gaps", [])):
        blockers.append("Representative Final question sources awaiting verification")
    reconciliation = release.manifest.get("heading_reconciliation", {})
    if reconciliation.get("status") != "complete" or reconciliation.get("expected_count") != reconciliation.get("accounted_count") or reconciliation.get("unresolved"):
        blockers.append("Expected textbook headings awaiting reconciliation")
    if release.status == "legacy": blockers.append("Legacy history cannot be activated as a textbook release")
    review_state = {"manifest_hash": release.manifest_hash,
        "members": [(n.node_id, n.paper_id, n.parent_id, n.level, n.name, n.seq) for n in nodes],
        "descriptors": [(r.node_id, r.revision, r.content_hash, approvals.get(r.id) == r.content_hash) for r in revisions],
        "spans": [(s.node_id, s.artifact_id, s.pdf_page_start, s.pdf_page_end, s.review_status, s.reviewed_by) for s in session.scalars(sa.select(NodeSourceSpan).where(NodeSourceSpan.taxonomy_version_id == release.taxonomy_version_id).order_by(NodeSourceSpan.id))],
        "crosswalk": [(m.old_node_id, m.new_node_id, m.relation, m.evidence, m.reviewed_by) for m in session.scalars(sa.select(TaxonomyCrosswalk).where(TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id).order_by(TaxonomyCrosswalk.id))]}
    return dict(version_id=version_id, manifest_hash=release.manifest_hash, review_hash=digest(review_state), approved_review_hash=release.approved_review_hash, status=release.status, node_count=len(nodes), eligible_count=len(eligible), source_count=len(sources), unresolved_sources=unresolved, unreviewed_descriptors=unreviewed, activation_ready=not blockers, blockers=blockers, legacy_progress_count=session.scalar(sa.select(sa.func.count()).select_from(Progress)) if include_personal_counts else None, legacy_note_count=session.scalar(sa.select(sa.func.count()).select_from(Note)) if include_personal_counts else None)


def approve_release(session: Session, version_id: str, manifest_hash: str, actor_id: int):
    session.execute(sa.text("SELECT pg_advisory_xact_lock(731306)"))
    require_administrator(session, actor_id)
    release = get_release(session, version_id)
    if release.manifest_hash != manifest_hash:
        raise ValueError("Manifest hash changed")
    report = release_report(session, version_id)
    if not report["activation_ready"]:
        raise ValueError("Release has unresolved review gates: " + "; ".join(report["blockers"]))
    release.approved_by, release.approved_at = actor_id, datetime.now(timezone.utc)
    release.approved_review_hash = report["review_hash"]
    if release.status != "active": release.status = "approved"
    session.flush()
    return release_report(session, version_id)


def activate_release(session: Session, version_id: str, manifest_hash: str, *, dry_run: bool = True):
    # The caller owns a single transaction encompassing validation + activation.
    session.execute(sa.text("SELECT pg_advisory_xact_lock(731306)"))
    release = session.scalar(sa.select(TaxonomyRelease).where(TaxonomyRelease.version_id == version_id).with_for_update())
    if release is None or release.manifest_hash != manifest_hash:
        raise ValueError("Approved manifest hash mismatch")
    report = release_report(session, version_id)
    if not report["activation_ready"] or release.approved_by is None or release.approved_review_hash != report["review_hash"]:
        raise ValueError("Administrator-approved release required")
    if not dry_run and release.status != "active":
        previous = active_version(session)
        if previous: previous.status = "archived"
        session.flush()
        release.status = "active"
        release.activated_at = datetime.now(timezone.utc)
        session.flush()
    return {**release_report(session, version_id), "dry_run": dry_run}


def migrate_exact_progress(session: Session, version_id: str, *, dry_run: bool = True) -> dict:
    release = get_release(session, version_id)
    mappings = list(session.scalars(sa.select(TaxonomyCrosswalk).where(TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id, TaxonomyCrosswalk.relation == "exact", TaxonomyCrosswalk.reviewed_by.is_not(None))))
    transferred = 0
    for mapping in mappings:
        if mapping.new_node_id is None or session.get(TaxonomyMember, (release.taxonomy_version_id, mapping.new_node_id)) is None:
            continue
        # Even reviewed split/merge-like many-to-one data never transfers state.
        conflicts = session.scalar(sa.select(sa.func.count()).select_from(TaxonomyCrosswalk).where(TaxonomyCrosswalk.taxonomy_version_id == release.taxonomy_version_id, sa.or_(TaxonomyCrosswalk.old_node_id == mapping.old_node_id, TaxonomyCrosswalk.new_node_id == mapping.new_node_id)))
        if conflicts != 1: continue
        for old in session.scalars(sa.select(Progress).where(Progress.node_id == mapping.old_node_id)):
            if session.get(Progress, (old.user_id, mapping.new_node_id)) or session.get(ProgressMigration, (old.user_id, mapping.id)):
                continue
            transferred += 1
            if not dry_run:
                session.add(Progress(user_id=old.user_id, node_id=mapping.new_node_id, status=old.status, status_changed_at=old.status_changed_at, first_done_at=old.first_done_at, last_revised_at=old.last_revised_at, verify_flag=old.verify_flag))
                session.add(ProgressMigration(user_id=old.user_id, crosswalk_id=mapping.id, original_snapshot={"node_id": old.node_id, "status": old.status}))
    session.flush()
    return {"dry_run": dry_run, "transferred": transferred, "notes_policy": "Original notes retained and linked with attribution"}
