"""Verify module colophons independently of filenames and applicability labels."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import time
import uuid

import httpx
import pymupdf
from selectolax.parser import HTMLParser

from caf_common.blob_store import BlobStore

ROOT = Path(__file__).parent


def main():
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text())
    identities = json.loads((ROOT / "identities.json").read_text())
    blobs = BlobStore(Path("data/blobs"))
    client = httpx.Client(timeout=60, follow_redirects=True)
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for audit in manifest["audit"]:
        url = audit["url"]
        cache = Path("data/textbook_v1") / (url.rsplit("/", 1)[1] + ".html")
        if not cache.exists():
            continue
        for anchor in HTMLParser(cache.read_text()).css("a"):
            if "initial" not in anchor.text().lower():
                continue
            download_url = anchor.attributes["href"].replace("http://", "https://")
            if any(r["download_url"] == download_url for r in records):
                continue
            raw = Path("data/textbook_v1") / download_url.rsplit("/", 1)[1]
            if not raw.exists():
                response = client.get(download_url)
                response.raise_for_status()
                if not response.content.startswith(b"%PDF"):
                    raise ValueError("Initial-page source was not a PDF")
                raw.write_bytes(response.content)
                time.sleep(5)
            sha, blob_path = blobs.put(raw.read_bytes())
            with pymupdf.open(blob_path) as pdf:
                text = " ".join(pdf[1].get_text().split())
                date = re.search(r"(?:Edition|Revised Edition)\s*:?\s*([A-Za-z]+),?\s*(20\d{2})", text)
                edition = " ".join(date.groups()) if date else "November 2024" if "November, 2024" in text else None
                reprint = re.search(r"Reprint\s*:?\s*([A-Za-z]+),?\s*(20\d{2})", text)
                records.append({"landing_url": url, "download_url": download_url, "sha256": sha,
                    "local_path": str(blob_path), "page_count": len(pdf), "pdf_page": 2,
                    "retrieved_at": now, "printed_edition": edition,
                    "reprint": " ".join(reprint.groups()) if reprint else None,
                    "edition_review": "colophon verified" if edition else "publication date requires review"})
    # The archive's October2023 edition is explicitly rejected as a fallback.
    rejected = Path("/private/tmp/P5archive-initial.pdf")
    if rejected.exists():
        sha, blob_path = blobs.put(rejected.read_bytes())
        with pymupdf.open(blob_path) as pdf:
            assert "October, 2023" in pdf[1].get_text()
            records.append({"landing_url": "https://www.icai.org/post/19168",
                "download_url": "https://resource.cdn.icai.org/76777bos61853-ip-mod1.pdf",
                "sha256": sha, "local_path": str(blob_path), "page_count": len(pdf),
                "pdf_page": 2, "printed_edition": "October 2023", "selected": False,
                "reason": "Does not match November2024 edition applicable January2026",
                "retrieved_at": now})
    manifest["module_colophon_audit"] = records
    for record in records:
        if record.get("selected") is False:
            continue
        sections = [a for a in manifest["textbook_artifacts"] if a["landing_url"] == record["landing_url"]]
        if not sections:
            continue
        selected = sections[0]
        key = f"artifact/{record['download_url']}"
        identities.setdefault(key, str(uuid.uuid4()))
        artifact_id = identities[key]
        if any(a["id"] == artifact_id for a in manifest["textbook_artifacts"]):
            continue
        manifest["textbook_artifacts"].append({"id": artifact_id,
            "paper_id": selected["paper_id"], "course_level": "Final",
            "edition": record["printed_edition"] or selected["edition"],
            "applicable_attempts": selected["applicable_attempts"],
            "landing_url": record["landing_url"], "download_url": record["download_url"],
            "sha256": record["sha256"], "local_path": record["local_path"],
            "retrieved_at": record["retrieved_at"], "page_count": record["page_count"],
            "edition_evidence": [record["landing_url"], record["download_url"]],
            "availability": "verified", "fallback": selected["fallback"],
            "target_applicability": selected["target_applicability"], "artifact_role": "front_matter",
            "expected_structure": [], "extracted_headings": [],
            "heading_reconciliation": {"status": "pending", "expected_count": 0,
                "accounted_count": 0, "unresolved": ["Front matter supplies edition/contents evidence and is excluded from conceptual nodes."]}})
    for artifact in manifest["textbook_artifacts"]:
        if artifact["fallback"] and artifact["paper_id"] != "s2023.P6":
            matching = [r for r in records if r["landing_url"] == artifact["landing_url"] and r["printed_edition"] == "November 2024"]
            artifact["edition_evidence"].extend(r["download_url"] for r in matching)
            artifact["edition_colophon_evidence"] = [{"download_url": r["download_url"], "sha256": r["sha256"], "pdf_page": 2, "printed_edition": r["printed_edition"]} for r in matching]
        if not artifact["fallback"]:
            matching = [r for r in records if r["landing_url"] == artifact["landing_url"] and r["printed_edition"]]
            artifact["publication_date_status"] = "colophon_verified" if matching else "requires_colophon_review"
            artifact["edition_colophon_evidence"] = [{"download_url": r["download_url"], "sha256": r["sha256"], "pdf_page": 2, "printed_edition": r["printed_edition"]} for r in matching]
            if matching:
                artifact["edition"] = matching[0]["printed_edition"]
                artifact["reprint"] = matching[0]["reprint"]
                if artifact["paper_id"] in {"s2023.P1", "s2023.P2", "s2023.P3"}:
                    artifact["applicability_basis"] = {"official_text": "Applicable for May 2026 Exam Onwards",
                        "official_url": f"https://www.icai.org/post/sm-final-paper{artifact['paper_id'][-1]}",
                        "interpretation": "May2027 is within the official ongoing applicability period; no superseding edition or limiting notice appears on the audited parent landing.",
                        "target_attempt": "2027-05"}
    by_artifact = {a["id"]: a for a in manifest["textbook_artifacts"]}
    for descriptor in manifest["descriptors"]:
        descriptor["edition"] = by_artifact[descriptor["source_spans"][0]["artifact_id"]]["edition"]
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2) + "\n")
    print("Verified module initial-page artifacts:", len(records))


if __name__ == "__main__":
    main()
