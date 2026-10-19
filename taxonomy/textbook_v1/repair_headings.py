"""Repair deterministic PDF heading boundaries without changing allocated IDs."""
from pathlib import Path
import json
import re
import uuid

import pymupdf

from caf_l0.sources import pdf_evidence

ROOT = Path(__file__).parent


def main():
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text())
    identities = json.loads((ROOT / "identities.json").read_text())
    excluded = set()
    repaired = []
    unit_nodes = []
    descriptors_by_node = {d["node_id"]: d for d in manifest["descriptors"]}
    for artifact in manifest["textbook_artifacts"]:
        if artifact["paper_id"] == "s2023.P6" or artifact.get("artifact_role") == "front_matter":
            continue
        _, count, headings = pdf_evidence(Path(artifact["local_path"]))
        with pymupdf.open(artifact["local_path"]) as pdf:
            exercise_pages = [i + 1 for i, page in enumerate(pdf) if "TEST YOUR KNOWLEDGE" in " ".join(page.get_text().split()).upper()]
        artifact["extracted_headings"] = [h.__dict__ for h in headings]
        topics = [n for n in manifest["nodes"] if n["kind"] == "topic" and
                  any(s["artifact_id"] == artifact["id"] for s in n["source_spans"])]
        missing = []
        for node in topics:
            span = node["source_spans"][0]
            matches = [h for h in headings if h.pdf_page == span["pdf_page_start"] and
                       (h.title == node["name"] or h.title.startswith(node["name"] + " ") or node["name"].startswith(h.title + " "))]
            if len(matches) != 1:
                excluded.add(node["id"])
                artifact.setdefault("excluded_headings", []).append({"name": node["name"],
                    "pdf_page": span["pdf_page_start"],
                    "reason": "Running header, example/exercise title, or ambiguous display-heading extraction"})
                continue
            heading = matches[0]
            if heading.title != node["name"]:
                old = node["name"]
                node["name"] = heading.title
                for key, value in list(identities.items()):
                    if value == node["id"]:
                        identities[key.replace(old, heading.title)] = value
                repaired.append({"node_id": node["id"], "before": old, "after": heading.title,
                                 "pdf_page": heading.pdf_page, "artifact_id": artifact["id"]})
            next_pages = [h.pdf_page for h in headings if h.pdf_page > heading.pdf_page]
            end = min(next_pages) if next_pages else count
            # Never include the exercise/answer region in a concept boundary.
            nearby_exercises = [p for p in exercise_pages if heading.pdf_page <= p <= end]
            if nearby_exercises:
                end = max(heading.pdf_page, min(nearby_exercises) - 1)
            span["pdf_page_end"] = end
            for leaf in manifest["nodes"]:
                if leaf["parent_id"] == node["id"] and leaf["kind"] == "subtopic":
                    leaf["source_spans"] = [dict(span)]
                    if heading.title != leaf["name"].upper():
                        leaf["name"] = heading.title.title()
                    descriptor = descriptors_by_node[leaf["id"]]
                    descriptor["source_spans"] = [dict(span)]
            if not any(n["name"] == heading.title for n in topics):
                missing.append(heading.title)
        artifact["heading_reconciliation"].update(status="pending", expected_count=len(headings),
            accounted_count=sum(n["id"] not in excluded for n in topics),
            unresolved=["Human contents/body heading reconciliation remains pending", *missing])
        print("Source repaired", artifact["paper_id"], "headings", len(headings), flush=True)
        # A chapter PDF may contain official units absent from its landing-page list.
        contexts = [n for n in manifest["nodes"] if n["kind"] == "chapter" and
                    any(s["artifact_id"] == artifact["id"] for s in n["source_spans"])]
        if not contexts:
            continue
        with pymupdf.open(artifact["local_path"]) as pdf:
            units = []
            for page_index, page in enumerate(pdf):
                blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
                for block_index, block in enumerate(blocks):
                    spans = [s for line in block["lines"] for s in line["spans"]]
                    text = " ".join(s["text"] for s in spans).strip()
                    match = re.match(r"^UNIT\s*(\d+)\s*:?\s*(.*)$", text, re.I)
                    if not match or not any(s["size"] >= 14 for s in spans):
                        continue
                    number, title = match.groups()
                    if not title and block_index + 1 < len(blocks):
                        following = blocks[block_index + 1]
                        title = " ".join(s["text"] for l in following["lines"] for s in l["spans"])
                    title = " ".join(title.split())
                    if title and not any(u[0] == number for u in units):
                        units.append((number, title, page_index + 1))
            for index, (number, title, page_start) in enumerate(units):
                key = f"pdf-unit/{artifact['id']}/{number}"
                identities.setdefault(key, str(uuid.uuid4()))
                unit_id = identities[key]
                page_end = units[index + 1][2] - 1 if index + 1 < len(units) else count
                unit = {"id": unit_id, "version_id": manifest["version_id"],
                    "paper_id": artifact["paper_id"], "parent_id": contexts[0]["id"], "kind": "unit",
                    "name": f"Unit {number}: {title}", "ordinal": int(number), "heading_origin": "official",
                    "source_spans": [{"artifact_id": artifact["id"], "pdf_page_start": page_start,
                                      "pdf_page_end": page_end, "review_status": "pending"}],
                    "source_review_status": "pending"}
                unit_nodes.append(unit)
                for topic in topics:
                    if topic["id"] not in excluded and page_start <= topic["source_spans"][0]["pdf_page_start"] <= page_end:
                        topic["parent_id"] = unit_id
                        topic["source_spans"][0]["pdf_page_end"] = min(topic["source_spans"][0]["pdf_page_end"], page_end)
                        for leaf in manifest["nodes"]:
                            if leaf["parent_id"] == topic["id"] and leaf["kind"] == "subtopic":
                                leaf["source_spans"] = [dict(topic["source_spans"][0])]
                                descriptors_by_node[leaf["id"]]["source_spans"] = [dict(topic["source_spans"][0])]
    excluded.update(n["id"] for n in manifest["nodes"] if n["parent_id"] in excluded)
    manifest["nodes"] = [n for n in manifest["nodes"] if n["id"] not in excluded]
    existing = {n["id"] for n in manifest["nodes"]}
    manifest["nodes"].extend(n for n in unit_nodes if n["id"] not in existing)
    manifest["descriptors"] = [d for d in manifest["descriptors"] if d["node_id"] not in excluded]
    manifest["heading_repair_audit"] = {"excluded_node_count": len(excluded),
        "joined_headings": repaired, "official_pdf_unit_count": len(unit_nodes),
        "review_status": "pending"}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2, ensure_ascii=False) + "\n")
    print({"excluded_node_count": len(excluded), "joined_heading_count": len(repaired), "official_pdf_unit_count": len(unit_nodes)})


if __name__ == "__main__":
    main()
