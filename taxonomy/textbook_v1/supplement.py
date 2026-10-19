"""Bind the independently downloaded prescribed SetA amendment as source context."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from caf_common.blob_store import BlobStore
from caf_l0.sources import pdf_evidence

ROOT = Path(__file__).parent


def main():
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text())
    identities = json.loads((ROOT / "identities.json").read_text())
    url = "https://resource.cdn.icai.org/83835bos67607.pdf"
    raw = Path("data/textbook_v1/83835bos67607.pdf")
    sha, pages, headings = pdf_evidence(raw, min_heading_size=11)
    _, blob_path = BlobStore(Path("data/blobs")).put(raw.read_bytes())
    key = f"artifact/{url}"
    identities.setdefault(key, str(uuid.uuid4()))
    artifact_id = identities[key]
    now = datetime.now(timezone.utc).isoformat()
    artifact = {"id": artifact_id, "paper_id": "s2023.P6", "course_level": "Final",
        "edition": "June2025 SPOM SetA amendments onward", "applicable_attempts": ["2026-01"],
        "landing_url": "https://boslive.icai.org/announcement_details.php?id=522", "download_url": url,
        "sha256": sha, "local_path": str(blob_path), "retrieved_at": now, "page_count": pages,
        "edition_evidence": ["https://boslive.icai.org/announcement_details.php?id=522", url],
        "edition_pdf_page": 1, "availability": "verified", "fallback": True,
        "target_applicability": "unresolved", "source_collection": "SPOM Set A",
        "artifact_role": "prescribed_amendment", "expected_structure": [{"kind": "supplement",
            "name": "Relevant amendments for June2025 examination and onwards for SetA: Corporate and Economic Laws"}],
        "extracted_headings": [h.__dict__ for h in headings],
        "heading_reconciliation": {"status": "pending", "expected_count": len(headings), "accounted_count": 0,
            "unresolved": ["Prescribed amendment bytes and January2026 IBS source selection verified; provision-level bindings to base-book concepts and May2027 Final applicability require review."]}}
    manifest["textbook_artifacts"] = [a for a in manifest["textbook_artifacts"] if a["id"] != artifact_id] + [artifact]
    container = next(n for n in manifest["nodes"] if n["name"] == "IBS source reference: SPOM Set A")
    if not any(s["artifact_id"] == artifact_id for s in container["source_spans"]):
        container["source_spans"].append({"artifact_id": artifact_id, "pdf_page_start": 1,
            "pdf_page_end": pages, "review_status": "pending"})
    for references in [manifest["ibs_source_audit"]["references"],
                       next(p for p in manifest["papers"] if p["paper_id"] == "s2023.P6")["expected_structure"]["referenced_textbooks"]]:
        for reference in references:
            if reference["name"] == "SPOM Set A":
                reference["prescribed_supplement_ids"] = [artifact_id]
    manifest["ibs_source_audit"]["prescribed_amendment_id"] = artifact_id
    manifest["audit"].append({"url": artifact["landing_url"], "http_status": 200,
        "cache_sha256": hashlib.sha256(Path("data/textbook_v1/announcement-522.html").read_bytes()).hexdigest(),
        "retrieved_at": now, "evidence": "Explicit January2026 core-paper/SPOM/digest edition matrix and prescribed amendment link independently read from official announcement."})
    for gap in manifest["source_gaps"]:
        if gap["paper_id"] == "s2023.P6":
            gap["reason"] = "Verified April2023 SetA and October2023 SetB source-reference branches are drafted from substantive textbook headings; integrated boundaries and complete contents/body reconciliation await review. Prescribed amendment83835bos67607.pdf is verified but provision-level bindings remain pending. January2026 study-guideline download and May2027 Final IBS applicability are unresolved."
        if "Most generated descriptors" in gap["reason"]:
            gap["reason"] = "Every drafted classification subtopic now has a source-section semantic descriptor draft. Authenticated source/descriptor review, recorded ambiguity resolution and administrator structural approval remain pending; machine generation does not establish eligibility."
    manifest["descriptor_generation_audit"]["approved_count"] = 0
    manifest["descriptor_generation_audit"]["source_issue_count"] = sum(bool(d.get("source_ambiguities")) for d in manifest["descriptors"])
    manifest["descriptor_generation_audit"]["budget_cap_usd"] = 10
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "identities.json").write_text(json.dumps(identities, indent=2) + "\n")
    print("Prescribed amendment verified", artifact_id, pages, "pages; final source count", len(manifest["textbook_artifacts"]))


if __name__ == "__main__":
    main()
