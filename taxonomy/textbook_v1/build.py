"""Rebuild the independent draft from audited official pages; UUIDs are persisted.

Run with `uv run taxonomy/textbook_v1/build.py`. Network access is explicit; the
script writes draft files and a local PDF cache, and never accesses the database.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import time
import uuid

import httpx
import pymupdf
from selectolax.parser import HTMLParser

from caf_l0.sources import pdf_evidence
from caf_common.blob_store import BlobStore

ROOT = Path(__file__).parent
CACHE = Path("data/textbook_v1")
VERSION = "textbook-v1"
JAN_EVIDENCE = "https://boslive.icai.org/announcement_details.php?id=522"
PAGES = {
    "P1": ["sm-final-p1-may2026"],
    "P2": ["sm-final-p2-may2026"],
    "P3": ["sm-final-p3-may2026"],
    "P4": ["sm-final-p4-may-nov2025", "sm-final-p4-may-nov2027"],
    "P5": ["sm-final-p5-may-nov-2027"],
    "P6": ["19442"],
}
NAMES = {
    "P1": "Financial Reporting", "P2": "Advanced Financial Management",
    "P3": "Advanced Auditing, Assurance and Professional Ethics",
    "P4": "Direct Tax Laws & International Taxation", "P5": "Indirect Tax Laws",
    "P6": "Integrated Business Solutions",
}


def save(name: str, value: object) -> None:
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def own_text(li: object) -> str:
    # selectolax HTML nodes expose a documented html/text contract.
    fragment = li.html.split("<ul", 1)[0]
    return " ".join(HTMLParser(fragment).text().split())


def structure(html: str) -> list[dict]:
    result = []
    module, chapter = None, None
    for li in HTMLParser(html).css("li"):
        name = own_text(li)
        kind = None
        if re.fullmatch(r"MODULE\s*-?\s*\d+", name, re.I):
            kind, module, chapter = "module", name, None
        elif re.match(r"Chapter\s*-?\s*\d+\s*:", name, re.I):
            kind, chapter = "chapter", name
        elif re.match(r"Unit\s*-?\s*\d+", name, re.I):
            kind = "unit"
        if not kind:
            continue
        link = li.css_first("a")
        url = None if link is None else link.attributes.get("href")
        published_url = url
        # ICAI's current P1 Unit6 anchor includes an accidental literal HTML
        # attribute in href. Keep the published value and verify the PDF URL.
        if url and url.endswith(".pdf rel="):
            url = url.removesuffix(" rel=")
        if kind == "module" or kind == "chapter" and li.css_first("ul") is not None:
            url = None
        result.append({"kind": kind, "name": name, "module": module,
                       "chapter": chapter, "download_url": url,
                       "published_download_url": published_url})
    return result


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    identity_path = ROOT / "identities.json"
    identities = json.loads(identity_path.read_text()) if identity_path.exists() else {}

    def identity(key: str) -> str:
        if key not in identities:
            identities[key] = str(uuid.uuid4())
            save("identities.json", identities)
        return identities[key]

    manifest = {"version_id": VERSION, "target_attempt": "2027-05", "status": "draft",
                "papers": [], "textbook_artifacts": [], "nodes": [], "descriptors": [],
                "crosswalk": [], "source_gaps": [], "audit": [],
                "official_weightages": [], "release_approval": None}
    client = httpx.Client(timeout=90, follow_redirects=True,
                         headers={"User-Agent": "CAFinalStudyCompanion/0.1 source audit"})
    retrieved = datetime.now(timezone.utc).isoformat()
    blobs = BlobStore(Path("data/blobs"))
    pages = {}
    for paper, slugs in PAGES.items():
        pages[paper] = []
        for slug in slugs:
            url = f"https://www.icai.org/post/{slug}"
            response = client.get(url)
            response.raise_for_status()
            (CACHE / f"{slug}.html").write_text(response.text)
            rows = structure(response.text)
            pages[paper].append((url, rows, "2027" in slug or paper in {"P1", "P2", "P3"}))
            manifest["audit"].append({"url": url, "retrieved_at": retrieved,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "http_status": response.status_code, "heading_count": len(rows)})
        manifest["papers"].append({"paper_id": f"s2023.{paper}", "name": NAMES[paper],
            "course_level": "Final", "selection_status": "partial" if paper in {"P4", "P5", "P6"} else "target_applicable",
            "expected_structure": pages[paper][0][1],
            "applicability_evidence": f"https://www.icai.org/post/sm-final-paper{paper[1]}" if paper in {"P1", "P2", "P3"} else JAN_EVIDENCE,
            "hierarchy_review_status": "pending", "classification_readiness": "unapproved"})
    save("manifest.json", manifest)  # six-paper source matrix precedes any nodes

    for paper, source_pages in pages.items():
        selected: dict[tuple[str, str | None, str | None], tuple] = {}
        for url, rows, target in source_pages:
            for row in rows:
                chapter_number = re.search(r"\d+", row["chapter"] or "")
                heading_number = re.search(r"\d+", row["name"])
                key = (row["kind"], chapter_number.group() if chapter_number else None,
                       heading_number.group() if heading_number else row["name"])
                selected[key] = (url, row, target)
        if paper == "P6":
            html = (CACHE / "19442.html").read_text()
            for anchor in HTMLParser(html).css("a"):
                if "IBS Case Study Digest" in anchor.text():
                    row = {"kind": "source_collection", "name": anchor.text(strip=True),
                           "module": None, "chapter": None,
                           "download_url": anchor.attributes["href"]}
                    selected[(row["kind"], None, row["name"])] = (source_pages[0][0], row, False)
            manifest["source_gaps"].append({"paper_id": "s2023.P6", "status": "unresolved",
                "reason": "SPOM Set A April 2023, Set B October 2023, January2026 guidelines and May2027 IBS applicability require source reconciliation. Core paper references are preserved, not duplicated as invented IBS modules."})
        node_lookup = {}
        for ordinal, (url, row, target) in enumerate(selected.values(), 1):
            kind, name = row["kind"], row["name"]
            ancestor = row["chapter"] if kind == "unit" else row["module"]
            parent = node_lookup.get(ancestor)
            node_key = f"{paper}/{row['module']}/{row['chapter']}/{kind}/{name}"
            node_id = identity(node_key)
            node_lookup[name] = node_id
            pdf_url = row["download_url"]
            node = {"id": node_id, "version_id": VERSION, "paper_id": f"s2023.{paper}",
                    "parent_id": parent, "kind": kind if kind != "source_collection" else "topic",
                    "name": name, "ordinal": ordinal, "heading_origin": "official",
                    "source_spans": [], "source_review_status": "pending"}
            if kind != "source_collection":
                manifest["nodes"].append(node)
            if not pdf_url:
                continue
            artifact_id = identity(f"artifact/{pdf_url}")
            artifact = {"id": artifact_id, "paper_id": f"s2023.{paper}",
                "course_level": "Final", "edition": "November 2024" if paper in {"P1", "P2", "P3"} else "May/November 2027" if target else "November 2024" if paper != "P6" else "July 2025" if "Volume" in name else "July 2024",
                "applicable_attempts": ["2027-05", "2027-11"] if target else ["2026-01"],
                "landing_url": url, "download_url": pdf_url, "sha256": None,
                "retrieved_at": retrieved, "page_count": None,
                "edition_evidence": [url, f"https://www.icai.org/post/sm-final-paper{paper[1]}"] if paper in {"P1", "P2", "P3"} else [url, JAN_EVIDENCE], "availability": "discovered",
                "fallback": not target, "target_applicability": "verified" if target else "unresolved",
                "expected_structure": [row], "heading_reconciliation": {
                    "status": "pending", "expected_count": 1, "accounted_count": 0,
                    "unresolved": ["Contents, outlines and body-heading reconciliation requires review"]},
                "instrument": "Income-tax Act, 2025" if paper == "P4" and target else "Income-tax Act, 1961" if paper == "P4" else None}
            manifest["textbook_artifacts"].append(artifact)
            path = CACHE / Path(pdf_url).name
            try:
                if not path.exists():
                    response = client.get(pdf_url)
                    response.raise_for_status()
                    if not response.content.startswith(b"%PDF"):
                        raise ValueError("Official URL did not return PDF bytes")
                    path.write_bytes(response.content)
                    time.sleep(5)
                digest, count, headings = pdf_evidence(path)
                blob_sha, blob_path = blobs.put(path.read_bytes())
                assert blob_sha == digest
                artifact.update(sha256=digest, page_count=count, availability="verified", local_path=str(blob_path))
                span = {"artifact_id": artifact_id, "pdf_page_start": 1,
                        "pdf_page_end": count, "review_status": "pending"}
                node["source_spans"] = [span]
                artifact["extracted_headings"] = [h.__dict__ for h in headings]
                # Cases are question evidence, not conceptual taxonomy labels.
                if kind == "source_collection":
                    continue
                for index, heading in enumerate(headings):
                    topic_id = identity(f"{node_key}/heading/{heading.number}/{heading.title}")
                    end = headings[index + 1].pdf_page if index + 1 < len(headings) else count
                    heading_span = {"artifact_id": artifact_id, "pdf_page_start": heading.pdf_page,
                                    "pdf_page_end": end, "review_status": "pending"}
                    topic = {"id": topic_id, "version_id": VERSION, "paper_id": f"s2023.{paper}",
                        "parent_id": node_id, "kind": "topic", "name": heading.title,
                        "ordinal": index + 1, "heading_origin": "official",
                        "source_spans": [heading_span], "source_review_status": "pending"}
                    manifest["nodes"].append(topic)
                    # Concept boundary drafts are explicitly app authored and await review.
                    leaf_id = identity(f"{node_key}/heading/{heading.number}/{heading.title}/concept")
                    leaf = dict(topic, id=leaf_id, parent_id=topic_id, kind="subtopic",
                                name=heading.title.title(), ordinal=1, heading_origin="app_authored")
                    manifest["nodes"].append(leaf)
                    manifest["descriptors"].append({"node_id": leaf_id, "revision": 1,
                        "definition": f"The textbook treatment of {heading.title.lower()} within {name}; the concept boundary is limited to the cited section and requires student review.",
                        "terminology": [heading.title.title()], "instrument_references": [artifact["instrument"]] if artifact["instrument"] else [],
                        "inclusion": [f"Questions testing the principles, conditions, calculations or application of {heading.title.lower()} in this section."],
                        "exclusion": ["Exclude neighbouring sections unless the complete question explicitly also tests their concepts. Exercise and answer headings are not classification concepts."],
                        "nearby_distinctions": [f"Use only the cited section of {name}; overlapping boundaries with adjacent numbered headings remain a review item."],
                        "source_spans": [heading_span], "edition": artifact["edition"],
                        "review_status": "pending", "draft_method": "numbered-display-heading draft"})
            except (httpx.HTTPError, ValueError, pymupdf.FileDataError) as error:
                artifact.update(availability="inaccessible", retrieval_error=str(error))
            save("manifest.json", manifest)
        print(paper, "complete draft; nodes", len(manifest["nodes"]), flush=True)
    manifest["source_gaps"].append({"paper_id": "s2023.P5", "status": "unresolved",
        "reason": "Only May2027 module1 chapters1-6 released. Official January2026 announcement expects4 modules; November2024 fallback download landing not yet verified. Do not substitute September2025/May2026 files."})
    manifest["source_gaps"].append({"paper_id": "all", "status": "pending_review",
        "reason": "Display-heading extraction is a draft. Contents, outlines, numbered body headings and substantive boundaries require full reconciliation; descriptor approval and source review are not inferred from download success."})
    # Container provenance is the union of verified descendant section evidence.
    for node in reversed(manifest["nodes"]):
        if not node["source_spans"]:
            seen_spans = set()
            for child in manifest["nodes"]:
                if child["parent_id"] == node["id"]:
                    for span in child["source_spans"]:
                        key = (span["artifact_id"], span["pdf_page_start"], span["pdf_page_end"])
                        if key not in seen_spans:
                            node["source_spans"].append(span)
                            seen_spans.add(key)
    unsupported = {n["id"] for n in manifest["nodes"] if not n["source_spans"]}
    for node in manifest["nodes"]:
        if node["id"] in unsupported:
            manifest["source_gaps"].append({"paper_id": node["paper_id"], "status": "unresolved",
                "expected_heading": node["name"], "reason": "No verified textbook page span; expected heading retained in inventory, not emitted as unsupported conceptual node"})
    manifest["nodes"] = [n for n in manifest["nodes"] if n["id"] not in unsupported]
    save("manifest.json", manifest)


if __name__ == "__main__":
    main()
