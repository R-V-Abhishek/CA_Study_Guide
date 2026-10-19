"""Audit the January2026 IBS-linked SPOM sources without inventing IBS modules."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import httpx
import pymupdf
from selectolax.parser import HTMLParser

from caf_common.blob_store import BlobStore
from caf_l0.sources import pdf_evidence
from build import structure

ROOT = Path(__file__).parent
CACHE = Path("data/textbook_v1")
SOURCES = [("Set A", "self-paced-online-modules-set-a-nset", "April 2023"),
           ("Set B", "19161", "October 2023")]


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    identities = json.loads((ROOT / "identities.json").read_text())
    blobs = BlobStore(Path("data/blobs"))
    now = datetime.now(timezone.utc).isoformat()
    refs = []
    for label, slug, edition in SOURCES:
        html = (CACHE / f"{slug}.html").read_text()
        # The SetB module names include their subject after the official number.
        rows = structure(html)
        if label == "Set A":
            for row in rows:
                row["part"] = "PART II: ECONOMIC LAWS" if row["kind"] == "chapter" and row["module"] == "MODULE 2" and "SEBI" not in row["name"] else "PART I: CORPORATE LAWS"
        if label == "Set B":
            for row in rows:
                number = int(row["name"].split(":")[0].split()[-1])
                row["module"] = "MODULE 1: STRATEGIC COST MANAGEMENT" if number <= 7 else "MODULE 2: STRATEGIC PERFORMANCE MANAGEMENT"
        urls = [a.attributes["href"] for a in HTMLParser(html).css("a")
                if "resource.cdn.icai.org" in a.attributes.get("href", "") and a.attributes["href"].endswith(".pdf")]

        def download(url):
            path = CACHE / url.rsplit("/", 1)[1]
            if not path.exists():
                response = httpx.get(url, timeout=90, follow_redirects=True)
                response.raise_for_status()
                if not response.content.startswith(b"%PDF"):
                    raise ValueError("SPOM source did not return PDF bytes")
                path.write_bytes(response.content)
            return url, path

        with ThreadPoolExecutor(max_workers=3) as pool:
            files = list(pool.map(download, urls))
        colophons = []
        for url, path in files:
            if "-ip-" not in url:
                continue
            with pymupdf.open(path) as pdf:
                text = " ".join(pdf[1].get_text().split())
                month, year = edition.split()
                if f"{month}, {year}" not in text:
                    raise ValueError(f"SPOM {label} colophon does not substantiate {edition}")
            sha, blob_path = blobs.put(path.read_bytes())
            colophons.append({"download_url": url, "sha256": sha, "local_path": str(blob_path),
                              "printed_edition": edition, "pdf_page": 2})
        artifact_ids = []
        for url, path in files:
            key = f"artifact/{url}"
            identities.setdefault(key, str(uuid.uuid4()))
            artifact_id = identities[key]
            artifact_ids.append(artifact_id)
            sha, count, headings = pdf_evidence(path)
            _, blob_path = blobs.put(path.read_bytes())
            expected = [row for row in rows if row["download_url"] == url]
            front = "-ip-" in url
            practice = "cp14.pdf" in url or url.endswith("-sa.pdf") or "appendix" in url
            artifact = {"id": artifact_id, "paper_id": "s2023.P6", "course_level": "Final",
                "edition": edition, "applicable_attempts": ["2026-01"],
                "landing_url": f"https://www.icai.org/post/{slug}", "download_url": url,
                "sha256": sha, "local_path": str(blob_path), "page_count": count,
                "retrieved_at": now, "edition_evidence": [f"https://www.icai.org/post/{slug}",
                    "https://boslive.icai.org/announcement_details.php?id=522"],
                "edition_colophon_evidence": colophons, "availability": "verified",
                "fallback": True, "target_applicability": "unresolved", "source_collection": f"SPOM {label}",
                "artifact_role": "front_matter" if front else "practice_collection" if practice else "textbook_section",
                "expected_structure": expected, "extracted_headings": [h.__dict__ for h in headings] if not front and not practice else [],
                "heading_reconciliation": {"status": "pending", "expected_count": len(headings) if not front and not practice else 0,
                    "accounted_count": 0, "unresolved": ["Referenced SPOM body concepts await IBS integration and source-context review; practice/case titles are excluded from taxonomy concepts."]}}
            manifest["textbook_artifacts"] = [a for a in manifest["textbook_artifacts"] if a["id"] != artifact_id]
            manifest["textbook_artifacts"].append(artifact)
        refs.append({"name": f"SPOM {label}", "edition": edition, "applicable_attempts": ["2026-01"],
            "landing_url": f"https://www.icai.org/post/{slug}", "sha256_landing": hashlib.sha256(html.encode()).hexdigest(),
            "expected_structure": rows, "expected_modules": ["MODULE 1", "MODULE 2"] if label == "Set A" else ["MODULE 1: STRATEGIC COST MANAGEMENT", "MODULE 2: STRATEGIC PERFORMANCE MANAGEMENT"],
            "artifact_ids": artifact_ids, "target_applicability": "unresolved"})
        print("IBS SPOM verified", label, len(files), "artifacts", flush=True)
    paper = next(p for p in manifest["papers"] if p["paper_id"] == "s2023.P6")
    paper["expected_structure"]["referenced_textbooks"] = refs
    manifest["ibs_source_audit"] = {"retrieved_at": now, "references": refs,
        "set_a_applicability_parent": "https://www.icai.org/post/bos-exam-spom-set-a",
        "target_issue": "SPOM SetA exam applicability changes from May2026; no verified May2027 Final IBS source notice supersedes the explicit January2026 Final IBS matrix. Keep the January2026 selected edition and unresolved target applicability distinct."}
    for gap in manifest["source_gaps"]:
        if gap["paper_id"] == "s2023.P6":
            gap["reason"] = "April2023 SetA and October2023 SetB colophons, chapter structures and PDF bytes verified. IBS integration of their substantive body headings, prescribed amendment83835bos67607.pdf, January2026 guidelines and May2027 Final IBS applicability remain unresolved. Digest case titles and SPOM exercises do not define taxonomy concepts."
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2) + "\n")


if __name__ == "__main__":
    main()
