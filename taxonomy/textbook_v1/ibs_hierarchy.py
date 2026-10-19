"""Draft unique IBS source-reference branches from verified SPOM textbook headings."""
import json
from pathlib import Path
import uuid

import pymupdf

from caf_l0.sources import pdf_evidence

ROOT = Path(__file__).parent


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    identities = json.loads((ROOT / "identities.json").read_text())
    sources = [a for a in manifest["textbook_artifacts"] if a.get("source_collection", "").startswith("SPOM ")]
    nodes, descriptors = [], []
    lookup = {}

    def node(key, name, kind, parent, spans, origin="official", ordinal=1):
        if key in lookup:
            return lookup[key]
        identities.setdefault(key, str(uuid.uuid4()))
        result = {"id": identities[key], "version_id": manifest["version_id"], "paper_id": "s2023.P6",
            "name": name, "kind": kind, "parent_id": parent["id"] if parent else None,
            "ordinal": ordinal, "heading_origin": origin, "source_spans": spans,
            "source_review_status": "pending", "source_reference_branch": True}
        lookup[key] = result
        nodes.append(result)
        return result

    for artifact in sources:
        if artifact["artifact_role"] != "textbook_section":
            continue
        row = artifact["expected_structure"][0]
        span = {"artifact_id": artifact["id"], "pdf_page_start": 1,
                "pdf_page_end": artifact["page_count"], "review_status": "pending"}
        collection = artifact["source_collection"]
        root = node(f"IBS/reference/{collection}", f"IBS source reference: {collection}", "topic", None, [], "app_authored")
        module = node(f"IBS/reference/{collection}/{row['module']}", row["module"], "module", root, [])
        parent = module
        if collection == "SPOM Set A":
            part = row["part"]
            parent = node(f"IBS/reference/{collection}/{row['module']}/{part}", part, "topic", module, [])
            if part == "PART I: CORPORATE LAWS":
                section = "SECTION A: COMPANY LAW" if row["module"] == "MODULE 1" else "SECTION B: SECURITIES LAWS"
                parent = node(f"IBS/reference/{collection}/{row['module']}/{section}", section, "topic", parent, [])
        chapter = node(f"IBS/reference/chapter/{artifact['id']}", row["name"], "chapter", parent, [dict(span)])
        _, _, headings = pdf_evidence(Path(artifact["local_path"]), min_heading_size=11, allow_lettered=collection == "SPOM Set B", allow_unnumbered="74859" in artifact["download_url"])
        artifact["extracted_headings"] = [h.__dict__ for h in headings]
        with pymupdf.open(artifact["local_path"]) as pdf:
            exercise_pages = [i + 1 for i, p in enumerate(pdf) if "TEST YOUR KNOWLEDGE" in " ".join(p.get_text().split()).upper()]
        for index, heading in enumerate(headings):
            end = headings[index + 1].pdf_page if index + 1 < len(headings) else artifact["page_count"]
            exercises = [p for p in exercise_pages if heading.pdf_page <= p <= end]
            if exercises:
                end = max(heading.pdf_page, min(exercises) - 1)
            concept_span = dict(span, pdf_page_start=heading.pdf_page, pdf_page_end=end)
            topic_parent = chapter
            if heading.instrument_context and heading.title == heading.instrument_context:
                node(f"IBS/instrument/{artifact['id']}/{heading.instrument_context}",
                    heading.instrument_context, "topic", chapter, [dict(span)])
                continue
            if heading.instrument_context:
                topic_parent = node(f"IBS/instrument/{artifact['id']}/{heading.instrument_context}",
                    heading.instrument_context, "topic", chapter, [dict(span)])
            if heading.section_context:
                topic_parent = node(f"IBS/section/{artifact['id']}/{heading.section_context}",
                    heading.section_context, "topic", chapter, [dict(span)])
                if heading.number.isalpha() and any(h.section_context == heading.section_context and h.number[0].isdigit() for h in headings):
                    continue
            key = f"IBS/heading/{artifact['id']}/{heading.instrument_context}/{heading.section_context}/{heading.number}/{heading.title}"
            topic = node(key, heading.title, "topic", topic_parent, [concept_span], ordinal=index + 1)
            leaf = node(key + "/concept", heading.title.title(), "subtopic", topic, [dict(concept_span)], "app_authored")
            descriptors.append({"node_id": leaf["id"], "revision": 1,
                "definition": f"The principles and application of {heading.title.lower()} within {row['name']}; a source-backed semantic draft is pending.",
                "terminology": [heading.title.title()],
                "instrument_references": [heading.instrument_context] if heading.instrument_context else [],
                "inclusion": [f"Application of the cited {heading.title.lower()} principles to an integrated business case."],
                "exclusion": ["Exclude worked-example and case-question titles, separately tested neighbouring concepts, and unverified target-attempt legal answers."],
                "nearby_distinctions": ["Retain this SPOM source context when the concept is absent from core Final papers; separately tag core-paper consequences through explicit cross-paper references."],
                "source_spans": [dict(concept_span)], "edition": artifact["edition"],
                "review_status": "pending", "draft_method": "verified-SPOM numbered-display-heading draft",
                "descriptor_quality": "boundary_draft_requires_substantive_review"})
        artifact["heading_reconciliation"] = {"status": "pending", "expected_count": len(headings),
            "accounted_count": len(headings), "unresolved": ["Extracted SPOM numbered/lettered headings drafted under explicit IBS reference context; contents/outline/body reconciliation and integrated classification boundaries require review."]}
        if not headings:
            manifest["source_gaps"].append({"paper_id": "s2023.P6", "status": "taxonomy_coverage_gap",
                "artifact_id": artifact["id"], "reason": f"No supported numbered concepts extracted from {row['name']}; substantive heading reconciliation is required."})
    # Reference/part/module context spans derive solely from their textbook children.
    for parent in reversed(nodes):
        if not parent["source_spans"]:
            parent["source_spans"] = [dict(s) for child in nodes if child["parent_id"] == parent["id"] for s in child["source_spans"]]
    prior = {n["id"] for n in manifest["nodes"] if n.get("source_reference_branch")}
    manifest["source_gaps"] = [g for g in manifest["source_gaps"] if not (g["status"] == "taxonomy_coverage_gap" and g.get("artifact_id") in {a["id"] for a in sources} and any(h for a in sources if a["id"] == g["artifact_id"] for h in a["extracted_headings"]))]
    manifest["nodes"] = [n for n in manifest["nodes"] if n["id"] not in prior] + nodes
    manifest["descriptors"] = [d for d in manifest["descriptors"] if d["node_id"] not in prior] + descriptors
    manifest["ibs_source_audit"]["draft_reference_nodes"] = len(nodes)
    manifest["ibs_source_audit"]["draft_reference_descriptors"] = len(descriptors)
    manifest["ibs_source_audit"]["taxonomy_coverage_status"] = "numbered-heading draft; full source reconciliation pending"
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2) + "\n")
    print("IBS verified SPOM reference draft", len(nodes), "nodes", len(descriptors), "descriptors")


if __name__ == "__main__":
    main()
