"""Shared PDF validation and immutable acquisition evidence for every import route."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import fitz

from caf_common.blob_store import BlobStore
from caf_l1.infer import ATTEMPT_REGEX, PAPER_REGEX, PAPER_NAMES, infer_metadata


@dataclass(frozen=True)
class VerifiedPDF:
    page_count: int
    has_text_layer: bool
    heading_text: str
    identity_text: str


def validate_pdf(data: bytes) -> VerifiedPDF:
    if not data.startswith(b"%PDF-"):
        raise ValueError("MISSING_PDF_HEADER")
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.is_encrypted:
                raise ValueError("ENCRYPTED_PDF")
            if not len(document):
                raise ValueError("EMPTY_PDF")
            text_pages = [page.get_text() for page in document]
            heading = "\n".join(text_pages[:3])
            lines = heading.splitlines()
            identity_lines = []
            for index, line in enumerate(lines):
                text = line.strip()
                level_heading = re.search(r"(?i)^(?:final|foundation|intermediate)$|(?:final|foundation|intermediate)\s+(?:examination|course)|\bca\.?\s+final\b", text)
                paper_heading = PAPER_REGEX.match(text)
                role_heading = re.search(r"(?i)revision test paper|suggested answer|model test paper|mock test paper|case study digest|study guideline|^question paper$", text)
                attempt_heading = ATTEMPT_REGEX.search(text) and (
                    ATTEMPT_REGEX.fullmatch(text) or re.search(r"(?i)examination|exam\b|applicable|relevant|onwards", text))
                if level_heading or role_heading or attempt_heading:
                    identity_lines.append(text)
                if paper_heading:
                    identity_lines.append(text)
                    for following in lines[index + 1:index + 4]:
                        subject = following.strip()
                        if subject.isupper() or subject.lower() in {name.lower() for name in PAPER_NAMES.values()}:
                            identity_lines.append(subject)
            return VerifiedPDF(len(document), any(len(text.strip()) > 20 for text in text_pages),
                               heading, "\n".join(identity_lines))
    except fitz.FileDataError as exc:
        raise ValueError(f"CORRUPT_PDF: {exc}") from exc


def validate_metadata(metadata: dict[str, Any], verified: VerifiedPDF) -> dict[str, Any]:
    """Retain hints while making content conflicts and combined-paper ranges explicit."""
    result = dict(metadata)
    heading_lines = "\n".join(verified.heading_text.splitlines()[:12])
    nonquestion = bool(re.search(r"(?im)^\s*(?:disclaimer\b|schedule\s+(?:of|for)|.*mock test.*schedule|login\s*$)", heading_lines))
    if nonquestion:
        result["doc_type_id"] = None
        result["artifact_role"] = "announcement"
        result["catalog_status"] = "needs_curation"
    content = infer_metadata("document.pdf", anchor_text=verified.identity_text)
    conflicts = []
    undated_source_collection = metadata.get("attempt_id") is None and metadata.get("doc_type_id") in {
        "model_question", "model_answer", "case_scenarios", "ibs_case_study"}
    for field in ("course_level", "attempt_id", "paper_id", "doc_type_id"):
        if field == "attempt_id" and undated_source_collection:
            continue  # Applicability statements on collection covers are not source attempts.
        hint, observed = result.get(field), content.get(field)
        if hint and observed and hint != observed:
            conflicts.append({"field": field, "navigation": hint, "content": observed})
        elif not hint and observed:
            result[field] = observed
    if nonquestion:
        result["doc_type_id"] = None
    ranges = result.get("paper_page_ranges") or []
    if len(content.get("paper_ids", [])) > 1:
        result["paper_ids"] = sorted(set(result.get("paper_ids") or []) | set(content["paper_ids"]))
    covered = set()
    for entry in ranges:
        paper = entry["paper_id"]
        first, last = entry["page_start"], entry["page_end"]
        if not paper.startswith(f"{result.get('scheme_id', 's2023')}.P"):
            raise ValueError("Paper range scheme mismatch")
        if first < 1 or last < first or last > verified.page_count:
            raise ValueError("Paper page range outside PDF bounds")
        pages = set(range(first, last + 1))
        if covered & pages:
            raise ValueError("Overlapping paper page ranges require administrator review")
        covered |= pages
    if ranges:
        # One content-addressed artifact can contain several distinct papers.
        result["paper_id"] = ranges[0]["paper_id"] if len(ranges) == 1 else None
    if result.get("paper_ids") and len(result["paper_ids"]) > 1 and not ranges:
        conflicts.append({"field": "paper_page_ranges", "reason": "combined_pdf_requires_page_ranges"})
        result["paper_id"] = None
    result["metadata_evidence"] = {"content_heading": verified.heading_text, "conflicts": conflicts,
                                   "content_identity_text": verified.identity_text, "content_checked": True}
    if undated_source_collection:
        result["attempt_id"] = None
        result["metadata_evidence"]["content_applicability"] = {
            "attempt_candidate": content.get("attempt_id"), "review_status": "pending",
            "statements": [line for line in verified.heading_text.splitlines()
                           if re.search(r"(?i)relevant|applicable|onwards", line)]}
    undated_collection = result.get("doc_type_id") in {"model_question", "model_answer"} or (
        result.get("doc_type_id") in {"case_scenarios", "ibs_case_study"} and result.get("collection_id"))
    complete = (not conflicts and result.get("course_level") == "final" and result.get("paper_id")
                and result.get("doc_type_id") and (result.get("attempt_id") or undated_collection))
    # Content matching is evidence, not an administrator's approval.
    result["catalog_status"] = "inferred" if complete else "needs_curation"
    return result


def record_observation(blob_store: BlobStore, digest: str, *, origin: str,
                       original_url: str | None, final_url: str | None,
                       metadata: dict[str, Any], response: dict[str, Any] | None = None,
                       previous_digest: str | None = None) -> Path:
    """Byte deduplication never discards distinct URL/manual source associations."""
    evidence = {"sha256": digest, "origin": origin, "original_url": original_url,
                "final_url": final_url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "response": response or {}, "metadata": metadata, "previous_sha256": previous_digest}
    folder = blob_store.base_dir / "acquisition" / digest[:2] / digest
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid4().hex}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
