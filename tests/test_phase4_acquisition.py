"""Deterministic source acquisition tests; only disposable harness DBs and mocked transport."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import fitz
import pytest
import sqlalchemy as sa

from caf_common.blob_store import BlobStore
from caf_db.models.ingest import DiscoveredLink, Document, SourcePage
from caf_l1.artifacts import validate_metadata, validate_pdf
from caf_l1.discover import DiscoveryFailure, LinkDiscoverer
from caf_l1.fetcher import DocumentFetcher
from caf_l1.importer import ManualImporter
from caf_l1.infer import infer_metadata
from caf_l1.inventory import enqueue_inventory, plan_inventory
from caf_l1.catalog import confirm_document


def pdf_bytes(text="FINAL\nQUESTION PAPER\nMAY 2024\nPaper 1\n1. Explain financial reporting.", pages=1):
    with fitz.open() as doc:
        for _ in range(pages):
            page = doc.new_page()
            page.insert_text((50, 70), text)
        return doc.tobytes()


@pytest.fixture
def polite():
    return SimpleNamespace(user_agent="test-agent", is_allowed=lambda url: True,
                           sleep_before_request=lambda url: None)


def hints(**overrides):
    return {"course_level": "final", "scheme_id": "s2023", "attempt_id": "2024-05",
            "paper_id": "s2023.P1", "doc_type_id": "question_paper", "catalog_status": "inferred", **overrides}


def test_content_metadata_conflicts_and_combined_ranges():
    native = validate_pdf(pdf_bytes("INTERMEDIATE\nMAY 2024\nPaper 1\nQUESTION PAPER", 2))
    meta = validate_metadata(hints(), native)
    assert meta["catalog_status"] == "needs_curation"
    assert meta["metadata_evidence"]["conflicts"][0]["field"] == "course_level"
    native = validate_pdf(pdf_bytes(pages=2))
    combined = validate_metadata(hints(paper_ids=["s2023.P1", "s2023.P2"]), native)
    assert combined["paper_id"] is None
    assert combined["metadata_evidence"]["conflicts"][-1]["reason"] == "combined_pdf_requires_page_ranges"
    with pytest.raises(ValueError, match="bounds"):
        validate_metadata(hints(paper_page_ranges=[{"paper_id": "s2023.P1", "page_start": 1, "page_end": 3}]), native)
    with pytest.raises(ValueError, match="Overlapping"):
        validate_metadata(hints(paper_page_ranges=[{"paper_id": "s2023.P1", "page_start": 1, "page_end": 2},
                                                  {"paper_id": "s2023.P2", "page_start": 2, "page_end": 2}]), native)


def test_schedule_and_cdn_are_not_question_evidence(polite):
    assert not LinkDiscoverer([], polite).is_pdf_url("https://resource.cdn.icai.org/login")
    assert LinkDiscoverer([], polite).is_pdf_url("https://resource.cdn.icai.org/paper.PDF?download=1")
    schedule = validate_metadata(hints(doc_type_id="mtp_question"), validate_pdf(pdf_bytes("Schedule of Mock Test Papers\nFinal\nMay 2024\nPaper 1")))
    assert schedule["doc_type_id"] is None
    assert schedule["artifact_role"] == "announcement"
    combined = infer_metadata("group.pdf", breadcrumb=["Final", "Paper 1 and Paper 2 Model Test Papers"])
    assert combined["paper_id"] is None
    assert combined["paper_ids"] == ["s2023.P1", "s2023.P2"]
    with pytest.raises(ValueError, match="MISSING_PDF_HEADER"):
        validate_pdf(b"<html>login</html>")


def test_manual_duplicates_preserve_source_receipts_and_group_metadata(tmp_path, session):
    store = BlobStore(tmp_path / "blobs")
    path = tmp_path / "group.pdf"
    path.write_bytes(pdf_bytes("Final\nModel Test Papers\nPaper 1 and Paper 2", 2))
    importer = ManualImporter(store)
    ranges = [{"paper_id": "s2023.P1", "page_start": 1, "page_end": 1},
              {"paper_id": "s2023.P2", "page_start": 2, "page_end": 2}]
    meta = hints(attempt_id=None, doc_type_id="model_question", collection_id="model-2026", paper_page_ranges=ranges)
    first = importer.import_file(path, session, overrides={**meta, "source_url": "https://example.invalid/one.pdf"})
    second = importer.import_file(path, session, overrides={**meta, "source_url": "https://example.invalid/two.pdf"})
    assert first.id == second.id
    assert first.paper_id is None and first.paper_page_ranges == ranges
    assert first.collection_id == "model-2026"
    receipts = [json.loads(file.read_text()) for file in store.base_dir.glob("acquisition/*/*/*.json")]
    assert {r["original_url"] for r in receipts} == {"https://example.invalid/one.pdf", "https://example.invalid/two.pdf"}
    assert len(receipts) == 2
    confirmed = confirm_document(session, first.id)
    assert confirmed.catalog_status == "confirmed"
    assert confirmed.metadata_evidence["administrator_confirmation"]["confirmed_at"]


def test_directory_import_reports_failures_without_losing_success(tmp_path, session):
    (tmp_path / "good.pdf").write_bytes(pdf_bytes())
    (tmp_path / "bad.pdf").write_bytes(b"HTML login")
    with pytest.raises(ValueError, match="failed imports: bad.pdf"):
        ManualImporter(BlobStore(tmp_path / "blobs")).import_directory(tmp_path, session)
    assert session.execute(sa.select(sa.func.count()).select_from(Document)).scalar_one() == 1


def test_inventory_routes_scope_and_enqueue_idempotent(tmp_path, session):
    records = []
    for index, (level, family, role, attempt) in enumerate([
        ("Foundation", "model", "question", None), ("Final", "model", "question", None),
        ("Final", "mock", "announcement", "2024-05"), ("Final", "past_exam", "question", "2023-11"),
        ("Final", "mock", "question", None)]):
        records.append({"id": str(index), "course_level": level, "source_family": family, "artifact_role": role,
                        "attempt_id": attempt, "scheme_id": "s2023", "paper_id": "s2023.P1", "paper_ids": [],
                        "doc_type_id": "model_question" if family == "model" else (None if role == "announcement" else "question_paper"),
                        "download_url": f"https://example.invalid/{index}.pdf", "landing_url": "https://example.invalid/final"})
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"records": records}))
    items = plan_inventory(path)
    assert [item.outcome for item in items] == ["outside_corpus", "pending", "not_question_artifact", "older_inventory", "needs_review"]
    assert enqueue_inventory(items, session) == 1
    assert enqueue_inventory(items, session) == 0
    assert len(plan_inventory(path, limit=2)) == 2
    assert plan_inventory(path, attempt_id="2023-11", include_older=True)[0].outcome == "pending"


def test_discovery_records_failures_iframes_and_rediscovery(monkeypatch, polite, session):
    monkeypatch.setattr("caf_l1.discover.assert_acquisition_allowed", lambda: None)
    discoverer = LinkDiscoverer([], polite)
    seed = {"id": "final", "url": "https://example.invalid/final", "max_depth": 2}
    pages = {seed["url"]: (200, seed["url"], '<title>Final May 2024</title><iframe src="/frame"></iframe>', {}),
             "https://example.invalid/frame": (200, "https://example.invalid/frame", '<a href="/paper.pdf">Paper 1 Question Paper</a>', {"etag": "v1"})}
    monkeypatch.setattr(discoverer, "_http_page", lambda client, url: pages[url])
    assert discoverer.discover_source(seed, session) == 1
    assert discoverer.last_outcome.documents_found == 1
    assert discoverer.discover_source(seed, session) == 0
    assert discoverer.last_outcome.status == "ok"
    assert session.execute(sa.select(SourcePage).where(SourcePage.url.endswith("/frame"))).scalar_one().etag == "v1"
    pages[seed["url"]] = (403, seed["url"], "login", {})
    with pytest.raises(DiscoveryFailure) as failed:
        discoverer.discover_source(seed, session)
    assert failed.value.outcome.status == "failed"
    assert session.execute(sa.select(SourcePage).where(SourcePage.url == seed["url"])).scalar_one().last_error == "HTTP_403"


def test_browser_isolated_context_and_explicit_zero_result(monkeypatch, polite, session):
    from playwright import sync_api
    monkeypatch.setattr("caf_l1.discover.assert_acquisition_allowed", lambda: None)
    actions = []
    class Page:
        url = "https://example.invalid/final"
        def goto(self, url, **kwargs):
            return SimpleNamespace(status=200, all_headers=lambda: {})
        def content(self):
            return "<title>Final</title><p>No published document</p>"
    class Context:
        def new_page(self):
            return Page()
        def close(self):
            actions.append("context_closed")
    class Browser:
        def new_context(self, **kwargs):
            actions.append("isolated_context")
            return Context()
        def close(self):
            actions.append("browser_closed")
    class Playwright:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: Browser()))
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(sync_api, "sync_playwright", Playwright)
    discoverer = LinkDiscoverer([], polite)
    with pytest.raises(DiscoveryFailure) as failed:
        discoverer.discover_source({"id": "browser", "url": Page.url, "mode": "browser"}, session)
    assert failed.value.outcome.status == "zero_documents"
    assert actions == ["isolated_context", "context_closed", "browser_closed"]
    assert session.execute(sa.select(SourcePage)).scalar_one().last_error == "NO_DOCUMENT_LINKS"


def test_http_changed_bytes_preserve_artifact_lineage_and_aliases(tmp_path, monkeypatch, polite, session):
    monkeypatch.setattr("caf_l1.fetcher.assert_acquisition_allowed", lambda: None)
    data = [pdf_bytes(), pdf_bytes("Final\nQuestion Paper\nMay 2024\nPaper 1\n1. Updated question.")]
    versions = iter([data[0], data[1], data[1]])
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return httpx.Response(200, content=next(versions), headers={"etag": "revision"},
                                  request=httpx.Request("GET", "https://example.invalid/final.pdf"))
    monkeypatch.setattr("caf_l1.fetcher.httpx.Client", Client)
    link = DiscoveredLink(url="https://example.invalid/paper.pdf", inferred=hints(), link_status="new")
    session.add(link)
    session.commit()
    fetcher = DocumentFetcher(BlobStore(tmp_path / "blobs"), polite)
    assert fetcher.fetch_pending(session) == 1
    previous_id = link.document_id
    assert fetcher.fetch_pending(session, refetch=True) == 1
    current = session.get(Document, link.document_id)
    assert current.id != previous_id
    assert current.supersedes_document_id == previous_id
    assert session.get(Document, previous_id).superseded is False
    assert fetcher.fetch_pending(session, refetch=True) == 0
    assert len(fetcher.last_report["associations"]) == 1
    receipts = [json.loads(file.read_text()) for file in fetcher.blob_store.base_dir.glob("acquisition/*/*/*.json")]
    assert len(receipts) == 3
    assert {receipt["final_url"] for receipt in receipts} == {"https://example.invalid/final.pdf"}
    assert receipts[0]["response"]["etag"] == "revision"
    assert session.execute(sa.select(sa.func.count()).select_from(Document)).scalar_one() == 2


def test_source_report_cached_artifacts_reverified_without_database(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from scripts import phase4_sources
    data = pdf_bytes()
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    existing = tmp_path / "existing"
    source_file = existing / digest[:2] / digest[2:4] / f"{digest}.pdf"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(data)
    record = {"id": "cached", "course_level": "Final", "source_family": "past_exam", "artifact_role": "question",
              "attempt_id": "2024-05", "scheme_id": "s2023", "paper_id": "s2023.P1", "paper_ids": ["s2023.P1"],
              "doc_type_id": "question_paper", "download_url": "https://resource.cdn.icai.org/test.pdf",
              "landing_url": "https://www.icai.org/final", "sha256": digest}
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"records": [record]}))
    report = tmp_path / "coverage.json"
    monkeypatch.setattr(phase4_sources, "assert_acquisition_allowed", lambda: None)
    arguments = ["--inventory", str(inventory), "--report", str(report), "--artifacts", str(tmp_path / "new"),
                 "--existing-blobs", str(existing)]
    result = CliRunner().invoke(phase4_sources.app, arguments)
    assert result.exit_code == 0, result.output
    saved = json.loads(report.read_text())
    assert saved["database_writes"] is False
    assert saved["human_confirmation_performed"] is False
    assert saved["records"][0]["sha256"] == digest
    assert saved["records"][0]["response"]["cache_reverified"] is True
    assert Path(saved["records"][0]["blob_path"]).read_bytes() == data
    result = CliRunner().invoke(phase4_sources.app, arguments)
    assert result.exit_code == 0, result.output
    resumed = json.loads(report.read_text())
    assert len(resumed["records"][0]["previous_observations"]) == 1
    assert resumed["records"][0]["metadata_confirmation"] == "pending"


def test_undated_collection_applicability_and_test_numbers_are_separate():
    native = validate_pdf(pdf_bytes("Final\nModel Test Paper 1\nFinancial Reporting\nRelevant for May 2025 onwards"))
    metadata = validate_metadata(hints(attempt_id=None, doc_type_id="model_question", collection_id="Model collection"), native)
    assert metadata["attempt_id"] is None
    assert metadata["metadata_evidence"]["content_applicability"]["attempt_candidate"] == "2025-05"
    inferred = infer_metadata("model.pdf", anchor_text="Final Model Test Paper 6 Financial Reporting")
    assert inferred["paper_id"] == "s2023.P1"
    assert inferred["paper_ids"] == []


def test_transport_failures_retain_retry_count_after_rollback(tmp_path, monkeypatch, polite, session):
    monkeypatch.setattr("caf_l1.fetcher.assert_acquisition_allowed", lambda: None)
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            raise httpx.ConnectError("transport unavailable")
    monkeypatch.setattr("caf_l1.fetcher.httpx.Client", Client)
    link = DiscoveredLink(url="https://example.invalid/error.pdf", inferred=hints(), link_status="new", tries=2)
    session.add(link)
    session.commit()
    fetcher = DocumentFetcher(BlobStore(tmp_path / "blobs"), polite)
    assert fetcher.fetch_pending(session) == 0
    assert link.tries == 3
    assert link.link_status == "failed"
    assert fetcher.last_report["failures"][0]["reason"] == "transport unavailable"


def test_transaction_dates_do_not_override_source_attempt():
    native = validate_pdf(pdf_bytes("FINAL EXAMINATION\nSUGGESTED ANSWERS MAY 2026\nPaper 1\nFinancial Reporting\n1. A company entered a transaction in November 2024 and paid in May 2025."))
    metadata = validate_metadata(hints(attempt_id="2026-05", doc_type_id="suggested_answer"), native)
    assert metadata["attempt_id"] == "2026-05"
    assert metadata["metadata_evidence"]["conflicts"] == []
    assert "November 2024" not in metadata["metadata_evidence"]["content_identity_text"]
