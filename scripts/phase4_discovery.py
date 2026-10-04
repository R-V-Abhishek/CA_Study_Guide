"""Artifact-only official navigation audit; writes a successor inventory without changing Phase 3."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import urldefrag, urljoin, urlparse
from uuid import NAMESPACE_URL, uuid5

import httpx
from selectolax.parser import HTMLParser
import typer

from caf_common.db_safety import assert_acquisition_allowed
from caf_l1.discover import _upgrade_redirect
from caf_l1.infer import infer_metadata
from caf_l1.robots import PolitenessManager

app = typer.Typer(pretty_exceptions_show_locals=False)


def extract_links(html, page_url):
    parser = HTMLParser(html)
    title = parser.css_first("title")
    title = title.text().strip() if title else ""
    links = []
    for node in parser.css("a, iframe, embed, object"):
        href = node.attributes.get("href") or node.attributes.get("src") or node.attributes.get("data")
        if not href:
            continue
        url, _ = urldefrag(urljoin(page_url, href))
        if url.startswith("http://"):
            url = "https://" + url[7:]
        if urlparse(url).scheme not in {"https", "http"}:
            continue
        context = node.parent.parent.text(separator=" ", strip=True) if node.parent and node.parent.parent else ""
        links.append((url, node.text().strip(), node.tag, context[:1500]))
    return title, links


@app.command()
def discover(
    original: Path = Path("taxonomy/textbook_v1/question_sources.json"),
    output: Path = Path("docs/Phase4_Additional_Sources.json"),
    merged: Path = Path("docs/Phase4_Acquisition_Inventory.json"),
    pages_dir: Path = Path("data/blobs/navigation"),
    max_pages: int = typer.Option(35, "--max-pages", min=1),
    browser: bool = typer.Option(True, "--browser/--no-browser", help="Try isolated Chromium when HTTP yields no mock PDFs"),
    cached_navigation: bool = typer.Option(True, "--cached-navigation/--fresh-navigation", help="Reparse hash-verified saved navigation when available"),
    browser_only: bool = typer.Option(False, "--browser-only", help="Audit just the mock portal in an isolated browser"),
    write_merged: bool = typer.Option(True, "--write-merged/--no-write-merged", help="Write a successor acquisition inventory"),
) -> None:
    assert_acquisition_allowed()
    defaults = tomllib.loads(Path("config/sources.toml").read_text())["defaults"]
    polite = PolitenessManager(defaults["user_agent"], defaults["min_delay_s"], defaults["max_delay_s"])
    seeds = [("past_exam", "https://www.icai.org/post/suggested-answer-final-course", 0, []),
             ("mock", "https://boslive.icai.org/education_content.php?p=Mock%20Test%20Papers", 0, []),
             ("ibs_evidence", "https://www.icai.org/post/19442", 0, [])]
    queue, seen, records, audits, gaps = list(seeds), set(), {}, [], []
    if browser_only:
        queue = []
    saved_audits = {}
    previous_browser_audits = []
    if cached_navigation and output.exists():
        previous_output = json.loads(output.read_text())
        previous_browser_audits = [audit for audit in previous_output.get("navigation_audits", [])
                                  if audit["mode"] == "browser"] + previous_output.get("previous_browser_audits", [])
        saved_audits = {audit["original_url"]: audit for audit in previous_output["navigation_audits"]
                        if audit["mode"] in {"http", "http_cache"}}
    pages_dir.mkdir(parents=True, exist_ok=True)
    def inspect_page(family, url, final_url, html, depth, crumbs, mode, status, observed_at=None):
        observed_at = observed_at or datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(html.encode()).hexdigest()
        path = pages_dir / f"{digest}.html"
        if not path.exists():
            path.write_text(html)
        title, links = extract_links(html, final_url)
        pdf_count = 0
        for target, anchor, tag, context in links:
            host = urlparse(target).hostname
            if urlparse(target).path.lower().endswith(".pdf") and host in defaults["pdf_hosts"]:
                pdf_count += 1
                branch_level = [] if family == "mock" else ["Final"]
                row_context = [context] if family == "mock" else []
                inferred = infer_metadata(target, anchor_text=anchor, breadcrumb=crumbs + [title, url] + row_context + branch_level)
                level = inferred["course_level"].capitalize() if inferred["course_level"] else ("Unresolved" if family == "mock" else "Final")
                announcement = bool(re.search(r"(?i)disclaimer|announcement|schedule|timetable|for students appearing", target + " " + context + " " + anchor))
                doc_type = "suggested_answer" if family == "past_exam" else inferred["doc_type_id"]
                if family == "mock" and not announcement and not doc_type:
                    doc_type = "mtp_answer" if re.search(r"(?i)answer|solution", anchor + " " + target) else "mtp_question"
                source_family = family
                if family == "ibs_evidence":
                    if (re.search(r'(?i)case\s+stud',anchor) or 'bos-notes-assignments-and-additional-guidance-content' in url) and not re.search(r'(?i)guideline|supplement',anchor):
                        doc_type = 'ibs_case_study' if 'digest' in anchor.lower() else 'case_scenarios'
                    source_family = "case_study" if doc_type in {"case_scenarios", "ibs_case_study"} else "supporting_evidence"
                    if "guideline" in anchor.lower():
                        doc_type = "study_guidelines"
                role = "announcement" if announcement else ("answer" if doc_type in {"suggested_answer", "mtp_answer"} else "question")
                if family == "ibs_evidence" and source_family == "supporting_evidence":
                    role = "evidence"
                identity = str(uuid5(NAMESPACE_URL, target))
                record = {"id": identity, "source_family": source_family, "course_level": level, "scheme_id": "s2023",
                          "attempt_id": inferred["attempt_id"], "paper_id": inferred["paper_id"],
                          "paper_ids": inferred.get("paper_ids") or ([inferred["paper_id"]] if inferred["paper_id"] else []),
                          "series": inferred["series"], "artifact_role": role, "doc_type_id": None if announcement else doc_type,
                          "landing_url": url, "download_url": target, "sha256": None, "page_count": None,
                          "availability": "discovered", "role_review_status": "pending_pdf_verification",
                          "classification_queue": "outside_corpus" if level in {"Foundation", "Intermediate"} else
                                                  ("not_question_artifact" if announcement or role == "evidence" else "final_queue"),
                          "title": anchor or Path(urlparse(target).path).name,
                          "retrieved_at": observed_at,
                          "navigation_evidence": {"page_sha256": digest, "page_path": str(path), "mode": mode,
                                                  "breadcrumb": crumbs + [title], "final_url": final_url}}
                group = re.search(r"(?i)\bgroup[\s_-]*(II|I|2|1)\b", anchor)
                if family == "past_exam" and group:
                    first_group = group.group(1).upper() in {"I", "1"}
                    record["group"] = "I" if first_group else "II"
                    record["paper_ids"] = [f"s2023.P{number}" for number in (range(1, 4) if first_group else range(4, 7))]
                    record["paper_id"] = None
                if family == "ibs_evidence":
                    record["paper_id"], record["paper_ids"] = "s2023.P6", ["s2023.P6"]
                    record["collection_id"] = anchor or "IBS official supporting collection"
                    record["attempt_id"] = None
                records[target] = record
            elif depth < 2 and host in {"www.icai.org", "boslive.icai.org"}:
                allowed_branch = ((family == "past_exam" and "sugg-ans-final" in target)
                                  or (family == "mock" and ("mtp" in target.lower() or "mock" in target.lower() or tag == "iframe"))
                                  or (family == 'ibs_evidence' and any(branch in target for branch in (
                                      'bos-case-published-stu-journal','bos-notes-assignments-and-additional-guidance-content'))))
                if allowed_branch and target not in seen:
                    queue.append((family, target, depth + 1, crumbs + [title or anchor]))
        audits.append({"source_family": family, "original_url": url, "final_url": final_url,
                       "http_status": status, "mode": mode, "page_sha256": digest, "page_path": str(path),
                       "pdf_links": pdf_count, "retrieved_at": observed_at,
                       "cache_reverified_at": datetime.now(timezone.utc).isoformat() if mode == "http_cache" else None})
        return pdf_count
    with httpx.Client(headers={"User-Agent": polite.user_agent}, timeout=30, follow_redirects=True,
                      event_hooks={"response": [_upgrade_redirect]}) as client:
        while queue and len(seen) < max_pages:
            family, url, depth, crumbs = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            cached = saved_audits.get(url)
            if cached and Path(cached["page_path"]).exists():
                html = Path(cached["page_path"]).read_bytes().decode("utf-8")
                if hashlib.sha256(html.encode()).hexdigest() == cached["page_sha256"]:
                    inspect_page(family, url, cached["final_url"], html, depth, crumbs, "http_cache",
                                 cached["http_status"], cached["retrieved_at"])
                    typer.echo(json.dumps({"url": url, "documents_so_far": len(records), "cached": True}))
                    continue
            if not polite.is_allowed(url):
                gaps.append({"source_family": family, "url": url, "outcome": "manual_required", "reason": "ROBOTS_DISALLOWED_NAVIGATION"})
                continue
            polite.sleep_before_request(url)
            try:
                response = client.get(url)
                if response.status_code != 200:
                    gaps.append({"source_family": family, "url": url, "outcome": "inaccessible", "reason": f"HTTP_{response.status_code}"})
                    continue
                inspect_page(family, url, str(response.url), response.text, depth, crumbs, "http", response.status_code)
                typer.echo(json.dumps({"url": url, "documents_so_far": len(records)}))
            except httpx.HTTPError as exc:
                gaps.append({"source_family": family, "url": url, "outcome": "inaccessible", "reason": str(exc)})
    if queue:
        gaps.append({"source_family": "past_exam", "outcome": "not_attempted", "reason": f"PAGE_LIMIT_REACHED:{max_pages}", "urls": [q[1] for q in queue]})
    current_mock_found = any(record["source_family"] == "mock" and record["course_level"] == "Final" and record["artifact_role"] != "announcement"
                            and record["attempt_id"] and record["attempt_id"] >= "2024-05"
                            for record in records.values())
    if browser and not current_mock_found:
        from playwright.sync_api import sync_playwright
        url = seeds[1][1]
        if polite.is_allowed(url):
            try:
                with sync_playwright() as playwright:
                    instance = playwright.chromium.launch(headless=True)
                    context = instance.new_context(user_agent=polite.user_agent)
                    try:
                        page = context.new_page()
                        polite.sleep_before_request(url)
                        response = page.goto(url, wait_until="networkidle", timeout=30000)
                        inspect_page("mock", url, page.url, page.content(), 0, [], "browser", response.status if response else 0)
                    finally:
                        context.close()
                        instance.close()
            except Exception as exc:
                gaps.append({"source_family": "mock", "url": url, "outcome": "browser_unavailable", "reason": str(exc)})
    for family in (("mock",) if browser_only else ("past_exam", "mock")):
        if not any(record["source_family"] == family and record["course_level"] == "Final" and record["artifact_role"] != "announcement" for record in records.values()):
            gaps.append({"source_family": family, "outcome": "zero_documents", "reason": "NO_QUESTION_OR_ANSWER_LINKS"})
    if not current_mock_found:
        gaps.append({"source_family": "mock", "outcome": "missing_expected_artifacts",
                     "reason": "No current dated mock question/answer artifacts confirmed in navigation; PDF roles require review"})
    output.parent.mkdir(parents=True, exist_ok=True)
    supplemental = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "audit_status": "partial" if gaps else "navigation_complete",
                    "records": list(records.values()), "navigation_audits": audits, "source_gaps": gaps,
                    "previous_browser_audits": previous_browser_audits,
                    "human_confirmation_performed": False, "original_inventory_unchanged": True}
    output.write_text(json.dumps(supplemental, indent=2))
    original_data = json.loads(original.read_text())
    known = {record["download_url"]: record for record in original_data["records"]}
    for record in records.values():
        known.setdefault(record["download_url"], record)
    successor = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "audit_status": "pending_acquisition",
                 "original_inventory_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                 "records": list(known.values()), "source_gaps": gaps}
    if write_merged:
        merged.write_text(json.dumps(successor, indent=2))
    typer.echo(json.dumps({"additional_records": len(records), "successor_records": len(known), "gaps": len(gaps), "output": str(output)}, indent=2))
    if gaps:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
