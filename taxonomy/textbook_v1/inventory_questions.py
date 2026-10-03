"""Audit separate question-source families without extracting the question corpus."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import hashlib
import json
import re
import time
import uuid

import httpx
import pymupdf
from selectolax.parser import HTMLParser

from caf_common.blob_store import BlobStore
from caf_l1.infer import infer_metadata

ROOT = Path(__file__).parent


def main():
    now = datetime.now(timezone.utc).isoformat()
    client = httpx.Client(timeout=60, follow_redirects=True)
    records, audits, gaps = [], [], []
    identities_path = ROOT / "question_identities.json"
    identities = json.loads(identities_path.read_text()) if identities_path.exists() else {}
    blobs = BlobStore(Path("data/blobs"))

    def identity(url):
        if url not in identities:
            identities[url] = str(uuid.uuid4())
            identities_path.write_text(json.dumps(identities, indent=2) + "\n")
        return identities[url]

    roots = []
    for level, slug in [("Foundation", "foundation"), ("Intermediate", "intermediate"), ("Final", "final")]:
        roots.append((level, "model", f"https://www.icai.org/post/{slug}-nset", 0))
        roots.append((level, "rtp", f"https://www.icai.org/post/rtp-{slug}-course", 0))
        roots.append((level, "past_exam", f"https://www.icai.org/post/question-papers-{slug}-course", 0))
    roots += [("Final", "mock", "https://boslive.icai.org/education_content.php?p=Mock%20Test%20Papers", 0),
              ("Final", "mock", "https://www.icai.org/post/final-mtp-may2023-sr1", 0),
              ("Final", "case_study", "https://www.icai.org/post/19442", 0)]
    seen = set()
    while roots:
        level, family, url, depth = roots.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            gaps.append({"course_level": level, "source_family": family, "url": url,
                         "availability": "inaccessible", "error": str(error)})
            continue
        audits.append({"url": url, "http_status": response.status_code,
                       "sha256": hashlib.sha256(response.content).hexdigest(), "retrieved_at": now})
        tree = HTMLParser(response.text)
        for anchor in tree.css("a"):
            href = anchor.attributes.get("href")
            if not href:
                continue
            href = urljoin(url, href).replace("http://", "https://")
            label = " ".join(anchor.text(strip=True).split())
            if family == "rtp" and depth == 0 and f"rtp-{level.lower()}-course-" in href and "hindi" not in href:
                roots.append((level, family, href, 1))
                continue
            if "resource.cdn.icai.org" not in href:
                continue
            context = " ".join(anchor.parent.parent.text(separator=" ", strip=True).split())[:1000]
            if family == "model" and "model test" not in label.lower():
                continue
            record_level = level
            if family == "mock" and "education_content.php" in url:
                record_level = "Foundation" if "foundation" in context.lower() else "Intermediate" if "intermediate" in context.lower() else "Final"
            if family == "mock" and ("announcement" in href.lower() or "education_content.php" in url):
                role = "announcement"
            else:
                role = "answer" if "answer" in label.lower() else "question"
            metadata = infer_metadata(href, label, [record_level, context, url])
            attempt = metadata["attempt_id"]
            if family == "model":
                attempt = None  # undated model booklets have no examination attempt
            old_scheme = "may2023" in url
            paper_id = metadata["paper_id"]
            if old_scheme and paper_id:
                paper_id = paper_id.replace("s2023", "s2017")
            group = "I" if "Group I" in label and "Group II" not in label else "II" if "Group II" in label else None
            if family == "model" and group:
                paper_id = None  # group booklets require section-specific metadata
            record = {"id": identity(href), "source_family": family, "course_level": record_level,
                "attempt_id": attempt, "scheme_id": "s2017" if old_scheme else "s2023",
                "paper_id": paper_id, "paper_ids": [f"s2023.P{i}" for i in ([1, 2, 3] if group == "I" else [4, 5, 6])] if level == "Final" and group else [],
                "group": group, "series": metadata["series"], "artifact_role": role,
                "paired_artifact_id": None, "availability": "discovered",
                "landing_url": url, "download_url": href, "sha256": None, "page_count": None,
                "classification_queue": "not_question_artifact" if role == "announcement" else "final_metadata_review" if record_level == "Final" else "outside_corpus",
                "retrieved_at": now, "title": label}
            record["doc_type_id"] = None if role == "announcement" else {
                "model": "model_answer" if role == "answer" else "model_question",
                "mock": "mtp_answer" if role == "answer" else "mtp_question",
                "rtp": "rtp", "past_exam": "suggested_answer" if role == "answer" else "question_paper",
                "case_study": "ibs_case_study"}[family]
            if not any(r["download_url"] == href for r in records):
                records.append(record)
        print(level, family, url, "records", len(records), flush=True)
        time.sleep(5)

    # Download a bounded representative set, keeping extraction a later phase.
    wanted = [next((r for r in records if r["course_level"] == "Final" and r["source_family"] == family and r["artifact_role"] != "announcement"), None) for family in ("model", "rtp", "mock")]
    for record in wanted:
        if record is None:
            continue
        try:
            response = client.get(record["download_url"])
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("Download returned non-PDF bytes")
            sha, path = blobs.put(response.content)
            with pymupdf.open(path) as document:
                record.update(sha256=sha, page_count=len(document), local_path=str(path), availability="verified")
        except (httpx.HTTPError, ValueError, pymupdf.FileDataError) as error:
            record.update(availability="inaccessible", error=str(error))
    # Link separate question/answer artifacts by source context, never by hash/name alone.
    for question in records:
        if question["artifact_role"] != "question" or not question["paper_id"]:
            continue
        answers = [r for r in records if r["artifact_role"] == "answer" and
                   all(r[k] == question[k] for k in ("paper_id", "attempt_id", "series", "landing_url"))]
        if len(answers) == 1:
            question["paired_artifact_id"] = answers[0]["id"]
            answers[0]["paired_artifact_id"] = question["id"]
    gaps.append({"source_family": "mock", "course_level": "Final", "availability": "missing",
                 "reason": "Current s2023 Mock Test question/answer artifacts were not exposed by the audited BoS page. May2023 s2017 papers are separately preserved and require scheme review, not passed to the new six-paper classifier."})
    payload = {"retrieved_at": now, "audit_status": "partial", "records": records, "audit": audits, "gaps": gaps}
    (ROOT / "question_sources.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
