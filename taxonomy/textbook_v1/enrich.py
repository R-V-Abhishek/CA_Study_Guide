"""Reconcile cached evidence and record source-backed concept boundary drafts."""
from pathlib import Path
import json
import re
import uuid

import pymupdf

from caf_common.blob_store import BlobStore

ROOT = Path(__file__).parent


def main():
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text())
    identities = json.loads((ROOT / "identities.json").read_text())

    def identity(key):
        if key not in identities:
            identities[key] = str(uuid.uuid4())
        return identities[key]

    artifacts = {a["id"]: a for a in manifest["textbook_artifacts"]}
    manifest["textbook_artifacts"] = list(artifacts.values())
    by_id = {n["id"]: n for n in manifest["nodes"]}
    blobs = BlobStore(Path("data/blobs"))
    for artifact in artifacts.values():
        if artifact["availability"] != "verified":
            continue
        sha, blob_path = blobs.put(Path(artifact["local_path"]).read_bytes())
        assert sha == artifact["sha256"]
        artifact["local_path"] = str(blob_path)
        headings = artifact["extracted_headings"]
        topics = [n for n in manifest["nodes"] if n["kind"] == "topic" and
                  any(s["artifact_id"] == artifact["id"] for s in n["source_spans"])]
        accounted = sum(any(n["name"] == h["title"] for n in topics) for h in headings)
        artifact["heading_reconciliation"] = {"status": "pending", "expected_count": len(headings),
            "accounted_count": accounted, "unresolved": [
                "Candidate display headings reconciled against emitted draft nodes; complete contents/outline/body-heading comparison and human concept-boundary review remain pending."]}
        # Repeated numbering and headings can be ambiguous in exercises/units.
        # Keep verified chapter/unit ancestry and record subdivision review instead
        # of joining nodes by a heading name or recycled number.
    # Only deepest concepts receive app-authored classification leaves.
    topic_parents = {n["parent_id"] for n in manifest["nodes"] if n["kind"] == "topic"}
    removed = {n["id"] for n in manifest["nodes"] if n["kind"] == "subtopic" and n["parent_id"] in topic_parents}
    manifest["nodes"] = [n for n in manifest["nodes"] if n["id"] not in removed]
    manifest["descriptors"] = [d for d in manifest["descriptors"] if d["node_id"] not in removed]
    by_id = {n["id"]: n for n in manifest["nodes"]}
    for descriptor in manifest["descriptors"]:
        node = by_id[descriptor["node_id"]]
        topic = by_id[node["parent_id"]]
        peers = [n["name"] for n in manifest["nodes"] if n["kind"] == "topic" and
                 n["parent_id"] == topic["parent_id"] and n["id"] != topic["id"]]
        descriptor["nearby_distinctions"] = [f"The cited section addresses {topic['name'].lower()}; {peer.lower()} has its own source boundary and must be tagged separately when tested." for peer in peers[:3]] or ["This concept inherits its chapter/unit context; cross-paper applications require explicit references, rather than name-based label transfer."]
        descriptor["descriptor_quality"] = "boundary_draft_requires_substantive_review"
    # IBS derives its integration concepts from the digest's curriculum explanation,
    # not its fifty questions or industry-case titles.
    ibs = next(a for a in artifacts.values() if a["paper_id"] == "s2023.P6" and "80945" in a["download_url"])
    with pymupdf.open(ibs["local_path"]) as pdf:
        assert "holistic view" in pdf[2].get_text().lower()
        assert "interrelated issues" in pdf[3].get_text().lower()
    span = {"artifact_id": ibs["id"], "pdf_page_start": 3, "pdf_page_end": 4, "review_status": "pending"}
    parent = identity("P6/integrated-business-decision-making")
    manifest["nodes"] = [n for n in manifest["nodes"] if n["paper_id"] != "s2023.P6"]
    prior_ibs_ids = {d["node_id"] for d in manifest["descriptors"] if d["node_id"] not in by_id or by_id[d["node_id"]]["paper_id"] == "s2023.P6"}
    manifest["descriptors"] = [d for d in manifest["descriptors"] if d["node_id"] not in prior_ibs_ids]
    manifest["nodes"].append({"id": parent, "version_id": manifest["version_id"],
        "paper_id": "s2023.P6", "parent_id": None, "kind": "topic",
        "name": "Integrated business decision-making", "ordinal": 1,
        "heading_origin": "app_authored", "source_spans": [span], "source_review_status": "pending"})
    concepts = [
        ("Holistic strategic decision-making", "Evaluate strategic choices using the business model, objectives, stakeholders, financial constraints and consequences across business functions. The case must connect these factors into a supported recommendation.", ["business model", "mission", "vision", "stakeholders", "strategic adaptation"], ["Multi-factor strategic recommendations and the interdependence of business decisions"], ["Isolated subject computations without an integrated decision"], ["Interrelated compliance analyses focus on reconciling regulatory consequences; this concept focuses on strategic choices and business impact."]),
        ("Interrelated finance, reporting, assurance and compliance", "Connect accounting, finance, assurance, taxation and company-law consequences within one business situation. Identify dependencies between the subject-specific issues and retain explicit links to their source-paper concepts.", ["integrated solution", "accounting standards", "assurance", "taxation", "company law", "professional values"], ["Cross-paper analysis of one complete case with separately tagged question parts"], ["Industry case names as conceptual classifications", "Historical tax answers treated as current without applicability review"], ["Strategic decision-making concerns choosing business actions; this concept concerns reconciling their financial and compliance implications."]),
    ]
    for ordinal, (name, definition, terms, inclusion, exclusion, distinctions) in enumerate(concepts, 1):
        node_id = identity("P6/integration/" + name)
        manifest["nodes"].append({"id": node_id, "version_id": manifest["version_id"],
            "paper_id": "s2023.P6", "parent_id": parent, "kind": "subtopic", "name": name,
            "ordinal": ordinal, "heading_origin": "app_authored", "source_spans": [span],
            "source_review_status": "pending", "cross_paper_references": [f"s2023.P{i}" for i in range(1, 6)]})
        manifest["descriptors"].append({"node_id": node_id, "revision": 1, "definition": definition,
            "terminology": terms, "inclusion": inclusion, "exclusion": exclusion,
            "nearby_distinctions": distinctions, "source_spans": [span], "review_status": "pending",
            "edition": "July 2024", "draft_method": "curriculum explanation on digest PDF pages3-4"})
    for paper in manifest["papers"]:
        if paper["paper_id"] == "s2023.P6":
            paper["expected_structure"] = {"conventional_modules": False,
                "official_sources": ["Final core papers1-5", "SPOM SetA April2023", "SPOM SetB October2023", "IBS Digest July2024", "IBS Digest VolumeII July2025", "January2026 study guidelines"],
                "source_references": [a["id"] for a in artifacts.values() if a["paper_id"] == "s2023.P6"]}
        if paper["paper_id"] == "s2023.P5":
            paper["expected_module_count"] = 4
            paper["expected_structure_status"] = "January2026 official matrix confirms4modules; absent fallback chapter/unit contents unresolved"
    manifest["source_gaps"].append({"paper_id": "all", "status": "pending_review",
        "reason": "Most generated descriptors are boundary drafts and need substantive definitions, terminology and inclusion/exclusion review before approval. Downloaded coverage is not classification readiness."})
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2, ensure_ascii=False) + "\n")
    print({"artifacts": len(artifacts), "nodes": len(manifest["nodes"]), "descriptors": len(manifest["descriptors"]), "gaps": len(manifest["source_gaps"])})


if __name__ == "__main__":
    main()
