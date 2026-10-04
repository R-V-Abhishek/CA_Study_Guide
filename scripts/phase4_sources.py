"""Acquire inventory artifacts and report live source outcomes without opening the application DB."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import tomllib
from typing import Any
from urllib.parse import urlparse

import httpx
import typer

from caf_common.blob_store import BlobStore
from caf_common.db_safety import assert_acquisition_allowed
from caf_l1.artifacts import record_observation, validate_metadata, validate_pdf
from caf_l1.fetcher import _upgrade_redirect
from caf_l1.inventory import plan_inventory
from caf_l1.robots import PolitenessManager

app = typer.Typer(pretty_exceptions_show_locals=False)


def _write_report(path: Path, records: list[dict[str, Any]], inventory_digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(record["outcome"] for record in records)
    scopes = Counter((record["course_level"], record["paper_id"] or "combined_or_unresolved",
                      record["attempt_id"] or record.get("collection_id") or "undated_unresolved",
                      record["source_family"], record["outcome"]) for record in records)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "inventory_sha256": inventory_digest,
              "database_writes": False, "human_confirmation_performed": False,
              "summary": dict(sorted(counts.items())),
              "coverage": [{"course_level": key[0], "paper_id": key[1], "attempt_or_collection": key[2],
                            "source_family": key[3], "outcome": key[4], "count": count}
                           for key, count in sorted(scopes.items())], "records": records}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    temporary.replace(path)


def _record(item, inventory_record):
    return {"inventory_id": item.inventory_id, "source_family": inventory_record["source_family"],
            "course_level": inventory_record["course_level"], "scheme_id": inventory_record["scheme_id"],
            "paper_id": inventory_record["paper_id"], "paper_ids": inventory_record["paper_ids"],
            "attempt_id": inventory_record["attempt_id"], "collection_id": item.metadata.get("collection_id"),
            "series": inventory_record.get("series"), "artifact_role": inventory_record["artifact_role"],
            "doc_type_id": inventory_record["doc_type_id"], "original_url": item.url,
            "landing_url": inventory_record["landing_url"], "outcome": item.outcome, "reason": item.reason,
            "artifact_acquired": False, "metadata_confirmation": "pending", "human_review": "pending"}


def _accept_artifact(record, data, store, metadata, *, origin, final_url, response, previous_digest=None):
    native = validate_pdf(data)
    validated = validate_metadata(metadata, native)
    digest, path = store.put(data)
    receipt = record_observation(store, digest, origin=origin, original_url=record["original_url"],
                                 final_url=final_url, metadata=validated, response=response,
                                 previous_digest=previous_digest)
    reasons = []
    if validated["catalog_status"] != "inferred":
        reasons.append("metadata_identity_requires_administrator_confirmation")
    if not validated.get("attempt_id") and validated.get("doc_type_id") not in {
            "model_question", "model_answer", "ibs_case_study", "case_scenarios"}:
        reasons.append("missing_source_attempt")
    if validated["metadata_evidence"]["conflicts"]:
        reasons.append("navigation_content_conflicts")
    if len(validated.get("paper_ids") or []) > 1 and not validated.get("paper_page_ranges"):
        reasons.append("combined_pdf_requires_paper_page_ranges")
    if not native.has_text_layer:
        reasons.append("native_text_unavailable_ocr_required")
    if metadata.get("artifact_role") == "evidence":
        record.update(outcome="supporting_evidence", reason="Applicability/guideline evidence requires separate administrator review")
    elif not validated.get("doc_type_id"):
        record.update(outcome="not_question_artifact", reason="PDF contents identify announcement or missing document role")
    else:
        record.update(outcome="metadata_review" if reasons else "acquired",
                      reason=", ".join(reasons) if reasons else None)
    record.update(artifact_acquired=True, sha256=digest, blob_path=str(path), page_count=native.page_count,
                  has_text_layer=native.has_text_layer, final_url=final_url, response=response,
                  metadata=validated, acquisition_receipt=str(receipt),
                  observed_at=datetime.now(timezone.utc).isoformat())


@app.command()
def acquire(
    inventory: Path = Path("taxonomy/textbook_v1/question_sources.json"),
    report: Path = Path("docs/Phase4_Source_Coverage.json"),
    artifacts: Path = Path("data/blobs"),
    existing_blobs: Path = Path("data/blobs"),
    limit: int = typer.Option(150, "--limit", min=1, help="Maximum uncached source downloads in this run"),
    timeout: float = typer.Option(20.0, "--timeout", min=1),
    dry_run: bool = typer.Option(False, "--dry-run"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    refresh_metadata: bool = typer.Option(False, "--refresh-metadata", help="Accept successor metadata only when existing source IDs and URLs remain identical"),
    verbose: bool = typer.Option(False, "--verbose", help="Log individual cache reverifications"),
) -> None:
    """Download current Final artifacts; retain explicit exclusions, failures, and review gaps."""
    inventory_data = json.loads(inventory.read_text())
    digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    records_by_id = {record["id"]: record for record in inventory_data["records"]}
    items = plan_inventory(inventory, limit=len(records_by_id))
    previous = {}
    if resume and report.exists():
        saved = json.loads(report.read_text())
        unchanged_source_urls = all(record["inventory_id"] in records_by_id and
                                    record["original_url"] == records_by_id[record["inventory_id"]]["download_url"]
                                    for record in saved["records"])
        allowed_metadata_refresh = refresh_metadata and unchanged_source_urls
        if (saved["inventory_sha256"] != digest and inventory_data.get("original_inventory_sha256") != saved["inventory_sha256"]
                and not allowed_metadata_refresh):
            raise ValueError("Inventory changed; supply --no-resume to create a fresh source audit")
        previous = {record["inventory_id"]: record for record in saved["records"]}
    records = [_record(item, records_by_id[item.inventory_id]) for item in items]
    for record in records:
        saved = previous.get(record["inventory_id"])
        if saved:
            history = list(saved.get("previous_observations", []))
            history.append({key: saved.get(key) for key in ("outcome", "reason", "observed_at", "attempts", "response", "discovery_robots_allowed",
                                                            "attempt_id", "collection_id", "paper_id", "paper_ids", "doc_type_id", "artifact_role", "sha256")})
            record["previous_observations"] = history
    if dry_run:
        typer.echo(json.dumps({"inventory_sha256": digest, "records": len(records),
                              "outcomes": dict(Counter(record["outcome"] for record in records)),
                              "network_download_limit": limit}, indent=2))
        return
    assert_acquisition_allowed()
    defaults = tomllib.loads(Path("config/sources.toml").read_text())["defaults"]
    allowed_hosts = set(defaults["pdf_hosts"])
    polite = PolitenessManager(defaults["user_agent"], defaults["min_delay_s"], defaults["max_delay_s"])
    store = BlobStore(artifacts)
    downloaded = 0
    failures = 0
    cached_urls = {}
    with httpx.Client(headers={"User-Agent": polite.user_agent}, timeout=timeout, follow_redirects=True,
                      event_hooks={"response": [_upgrade_redirect]}) as client:
        for index, (item, record) in enumerate(zip(items, records)):
            source = records_by_id[item.inventory_id]
            if item.outcome in {"outside_corpus", "older_inventory", "not_question_artifact", "source_gap"}:
                continue
            if not item.url:
                record.update(outcome="source_gap", reason="No download URL")
                continue
            if urlparse(item.url).hostname not in allowed_hosts:
                record.update(outcome="inaccessible", reason="Download URL outside configured official PDF hosts")
                failures += 1
                continue
            cached = previous.get(item.inventory_id) or cached_urls.get(item.url)
            cache_path = Path(cached["blob_path"]) if cached and cached.get("artifact_acquired") else None
            expected = cached.get("sha256") if cached else source.get("sha256")
            if not cache_path and expected:
                candidate = existing_blobs / expected[:2] / expected[2:4] / f"{expected}.pdf"
                cache_path = candidate if candidate.exists() else None
            cache_error = None
            if cache_path and cache_path.exists():
                data = cache_path.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual == expected:
                    try:
                        _accept_artifact(record, data, store, item.metadata, origin="assisted",
                            final_url=cached.get("final_url", item.url) if cached else item.url,
                            response={**(cached.get("response", {}) if cached else {}), "cache_reverified": True},
                            previous_digest=expected)
                        cached_urls[item.url] = record
                        _write_report(report, records, digest)
                        if verbose:
                            typer.echo(json.dumps({"index": index + 1, "total": len(records), "outcome": record["outcome"], "cached": True, "id": item.inventory_id}))
                        continue
                    except ValueError as exc:
                        cache_error = str(exc)
                else:
                    cache_error = "Cached bytes do not match their recorded SHA256"
            if downloaded >= limit:
                record.update(outcome="not_attempted", reason="Run download limit reached", cache_error=cache_error)
                continue
            downloaded += 1
            # Match DocumentFetcher: inventory URLs are already discovered public artifacts;
            # robots controls automatic navigation, while direct acquisition keeps host delays.
            record["discovery_robots_allowed"] = polite.is_allowed(item.url)
            attempts = []
            success = False
            for attempt in range(1, 4):
                polite.sleep_before_request(item.url)
                try:
                    response = client.get(item.url)
                    observation = {"try": attempt, "status": response.status_code, "final_url": str(response.url),
                                   "etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified"),
                                   "content_type": response.headers.get("content-type"), "bytes": len(response.content),
                                   "retrieved_at": datetime.now(timezone.utc).isoformat()}
                    attempts.append(observation)
                    if response.status_code == 200:
                        _accept_artifact(record, response.content, store, item.metadata, origin="http",
                                         final_url=str(response.url), response=observation, previous_digest=expected)
                        success = True
                        cached_urls[item.url] = record
                        break
                    record.update(outcome="inaccessible", reason=f"HTTP_{response.status_code}", final_url=str(response.url))
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        break
                except httpx.HTTPError as exc:
                    attempts.append({"try": attempt, "error": str(exc), "retrieved_at": datetime.now(timezone.utc).isoformat()})
                    record.update(outcome="inaccessible", reason=str(exc))
                except ValueError as exc:
                    attempts.append({"try": attempt, "error": str(exc), "retrieved_at": datetime.now(timezone.utc).isoformat()})
                    record.update(outcome="inaccessible", reason=str(exc))
                    break
                if attempt < 3:
                    time.sleep(2 ** attempt)
            record["attempts"] = attempts
            if cache_error:
                record["cache_error"] = cache_error
            if not success:
                failures += 1
            _write_report(report, records, digest)
            typer.echo(json.dumps({"index": index + 1, "total": len(records), "outcome": record["outcome"], "cached": False, "id": item.inventory_id}))
    _write_report(report, records, digest)
    typer.echo(json.dumps({"downloads_attempted": downloaded, "inaccessible": failures,
                          "summary": dict(Counter(record["outcome"] for record in records)), "report": str(report)}, indent=2))
    if failures or any(record["outcome"] == "not_attempted" for record in records):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
