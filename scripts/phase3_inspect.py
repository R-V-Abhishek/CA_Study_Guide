"""Read-only evidence for source payloads and the installed unapproved release."""

import json
from pathlib import Path
from time import perf_counter

import sqlalchemy as sa
from sqlalchemy.orm import Session
import typer

from caf_api.taxonomy import tree
from caf_contracts.taxonomy import TaxonomyTreeNode
from caf_db.engine import get_engine
from caf_db.models.taxonomy import NodeSourceSpan, TextbookArtifact
from caf_l0.hierarchy import version_nodes as serving_nodes
from caf_l0.manifest import load_manifest
from caf_l0.releases import active_version, digest, get_release, release_report, span_context

app = typer.Typer()


def serialized_bytes(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


@app.command("payload")
def payload(manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json"),
            report: Path = Path("docs/Phase3_Source_Payload.json")):
    manifest = load_manifest(manifest_path)
    artifacts = {value["id"]: TextbookArtifact(id=value["id"], edition=value["edition"],
        availability=value["availability"], metadata_json=value)
        for value in manifest["textbook_artifacts"]}
    original = []
    projected = []
    for node in manifest["nodes"]:
        for value in node["source_spans"]:
            span = NodeSourceSpan(**value)
            artifact = artifacts[span.artifact_id]
            original.append({**artifact.metadata_json, "artifact_id": artifact.id,
                "pdf_page_start": span.pdf_page_start, "pdf_page_end": span.pdf_page_end,
                "review_status": span.review_status})
            projected.append(span_context(span, artifact))
    result = dict(manifest_hash=digest(manifest), source_span_count=len(projected),
        previous_repeated_metadata_bytes=serialized_bytes(original),
        explorer_source_metadata_bytes=serialized_bytes(projected),
        full_inventory_preserved_in_admin_endpoint=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(json.dumps(result, indent=2))


@app.command("runtime")
def runtime(manifest_path: Path = Path("taxonomy/textbook_v1/manifest.json"),
            report: Path = Path("docs/Phase3_Runtime_Inspection.json")):
    manifest = load_manifest(manifest_path)
    with Session(get_engine("student")) as session, session.begin():
        session.execute(sa.text("SET TRANSACTION READ ONLY"))
        release = get_release(session, manifest["version_id"])
        if release.manifest_hash != digest(manifest):
            raise ValueError("Installed release does not match the source bundle")
        started = perf_counter()
        roots = [TaxonomyTreeNode.model_validate(value).model_dump(mode="json")
                 for value in tree(release.version_id, db=session)]
        elapsed = perf_counter() - started
        nodes = []
        pending = list(roots)
        while pending:
            node = pending.pop()
            nodes.append(node)
            pending.extend(node["children"])
        if {node["id"] for node in nodes} != {node["id"] for node in manifest["nodes"]}:
            raise ValueError("Runtime tree membership differs from immutable manifest")
        active = active_version(session)
        legacy = get_release(session, "legacy")
        legacy_ids = {node.id for node in serving_nodes(session, legacy.taxonomy_version_id)}
        current_ids = {node.id for node in serving_nodes(session)}
        if active is None and current_ids != legacy_ids:
            raise ValueError("The draft changed the serving legacy hierarchy")
        if legacy_ids.intersection(node["id"] for node in nodes):
            raise ValueError("Rebuilt taxonomy reuses legacy identities")
        result = dict(version_id=release.version_id, manifest_hash=release.manifest_hash,
            status=release.status, active_taxonomy_version=active.version_id if active else None,
            legacy_node_count=len(legacy_ids), serving_node_count=len(current_ids),
            tree_node_count=len(nodes), eligible_subtopics=sum(node["eligible"] for node in nodes),
            tree_response_bytes=serialized_bytes(roots), tree_load_seconds=round(elapsed, 3),
            student_database_role=session.scalar(sa.text("SELECT current_user")),
            personal_history_transferred=False, activation_performed=False)
        if release.status != "draft" or result["eligible_subtopics"]:
            raise ValueError("Expected an unreviewed draft with no eligible classifier candidates")
    with Session(get_engine("operations")) as session, session.begin():
        session.execute(sa.text("SET TRANSACTION READ ONLY"))
        result["operations_database_role"] = session.scalar(sa.text("SELECT current_user"))
        result["release_report"] = release_report(session, manifest["version_id"], include_personal_counts=False)
    report.write_text(json.dumps(result, indent=2, default=str) + "\n")
    typer.echo(json.dumps({key: value for key, value in result.items() if key != "release_report"}, indent=2))


if __name__ == "__main__":
    app()
