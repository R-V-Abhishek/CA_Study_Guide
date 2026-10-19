"""Bounded HTTP and isolated-browser discovery with explicit source outcomes."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urljoin, urldefrag, urlparse

import httpx
from selectolax.parser import HTMLParser
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.db_safety import assert_acquisition_allowed
from caf_common.logging import get_logger
from caf_l1.infer import infer_metadata
from caf_l1.robots import PolitenessManager
from caf_db.models.ingest import DiscoveredLink, SourcePage
from caf_db.models.ops import Event

logger = get_logger("acquire.discover")


def _upgrade_redirect(response: httpx.Response) -> None:
    if response.is_redirect:
        location = response.headers.get("location", "")
        if location.startswith("http://"):
            response.headers["location"] = "https://" + location[7:]


@dataclass
class DiscoveryOutcome:
    source_id: str
    status: str = "running"
    pages_checked: int = 0
    documents_found: int = 0
    new_links: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)


class DiscoveryFailure(RuntimeError):
    def __init__(self, outcome: DiscoveryOutcome):
        self.outcome = outcome
        super().__init__(f"Discovery {outcome.source_id}: {outcome.status}; {outcome.failures}")


class LinkDiscoverer:
    def __init__(self, sources: list[dict[str, Any]], politeness: PolitenessManager) -> None:
        self.sources = sources
        self.politeness = politeness
        self.last_outcome: DiscoveryOutcome | None = None

    def is_pdf_url(self, url: str) -> bool:
        # A CDN also serves schedules, HTML and images; its hostname is not PDF evidence.
        return urlparse(url).path.lower().endswith(".pdf")

    def _record_page(self, session, source_id, url, depth, parent, mode, allowed,
                     status=None, error=None, headers=None):
        page = session.execute(sa.select(SourcePage).where(SourcePage.url == url)).scalar_one_or_none()
        if page is None:
            page = SourcePage(source_id=source_id, url=url, depth=depth, parent_page_id=parent,
                              fetch_mode=mode, robots_allowed=allowed, link_count=0)
            session.add(page)
            session.flush()
        page.last_fetched_at = datetime.now(timezone.utc)
        page.http_status = status
        page.last_error = error
        page.fetch_mode = mode
        page.robots_allowed = allowed
        page.etag = (headers or {}).get("etag")
        page.last_modified = (headers or {}).get("last-modified")
        return page

    def discover_source(self, source: dict[str, Any], session: Session,
                        run_id: int | None = None) -> int:
        assert_acquisition_allowed()
        outcome = DiscoveryOutcome(source_id=source["id"])
        self.last_outcome = outcome
        mode = source.get("mode", "http")
        if mode not in {"http", "browser", "assisted"}:
            raise ValueError(f"Unsupported discovery mode: {mode}")
        if mode == "assisted":
            outcome.status = "manual_required"
            outcome.failures.append({"url": source["url"], "reason": "Assisted source requires an imported artifact"})
            self._record_page(session, source["id"], source["url"], 0, None, mode, None,
                              error="MANUAL_REQUIRED")
            session.commit()
            raise DiscoveryFailure(outcome)
        try:
            if mode == "browser":
                self._discover_browser(source, session, outcome)
            else:
                with httpx.Client(headers={"User-Agent": self.politeness.user_agent}, timeout=15,
                                  follow_redirects=True, event_hooks={"response": [_upgrade_redirect]}) as client:
                    self._crawl(source, session, outcome, lambda url: self._http_page(client, url))
        except DiscoveryFailure:
            raise
        except Exception as exc:
            outcome.failures.append({"url": source["url"], "reason": str(exc)})
            self._record_page(session, source["id"], source["url"], 0, None, mode, None,
                              error=f"DISCOVERY_UNAVAILABLE: {exc}")
            session.commit()
        outcome.status = "partial" if outcome.documents_found and outcome.failures else "ok"
        if not outcome.documents_found:
            outcome.status = "failed" if outcome.failures else "zero_documents"
            if not outcome.failures:
                outcome.failures.append({"url": source["url"], "reason": "NO_DOCUMENT_LINKS"})
            if run_id is not None:
                session.add(Event(run_id=run_id, level="warn", code="L1_DISCOVERY_FAILED",
                                  message=str(outcome.failures)))
                session.commit()
            raise DiscoveryFailure(outcome)
        return outcome.new_links

    def _http_page(self, client, url):
        response = client.get(url)
        return response.status_code, str(response.url), response.text, dict(response.headers)

    def _discover_browser(self, source, session, outcome):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(user_agent=self.politeness.user_agent)
            try:
                page = context.new_page()
                def fetch(url):
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    return response.status if response else 0, page.url, page.content(), response.all_headers() if response else {}
                self._crawl(source, session, outcome, fetch)
            finally:
                context.close()
                browser.close()

    def _crawl(self, source, session, outcome, fetch):
        seed = source["url"]
        if seed.startswith("http://"):
            seed = "https://" + seed[7:]
        mode = source.get("mode", "http")
        max_depth = source.get("max_depth", 2)
        max_pages = source.get("max_pages", 100)
        patterns = [re.compile(pattern) for pattern in source.get("follow_patterns", [])]
        queue = [(seed, 0, [], None)]
        seen = {seed}
        documents = set()
        while queue and outcome.pages_checked < max_pages:
            url, depth, crumbs, parent = queue.pop(0)
            outcome.pages_checked += 1
            allowed = self.politeness.is_allowed(url)
            if not allowed:
                self._record_page(session, source["id"], url, depth, parent, mode, False,
                                  error="ROBOTS_DISALLOWED")
                outcome.failures.append({"url": url, "reason": "ROBOTS_DISALLOWED"})
                session.commit()
                continue
            self.politeness.sleep_before_request(url)
            try:
                status, final_url, html, headers = fetch(url)
            except Exception as exc:
                self._record_page(session, source["id"], url, depth, parent, mode, True,
                                  error=f"FETCH_FAILED: {exc}")
                outcome.failures.append({"url": url, "reason": str(exc)})
                session.commit()
                continue
            error = None if status == 200 else f"HTTP_{status}"
            page = self._record_page(session, source["id"], url, depth, parent, mode, True,
                                     status, error, headers)
            if error:
                outcome.failures.append({"url": url, "reason": error})
                session.commit()
                continue
            parser = HTMLParser(html)
            title_node = parser.css_first("title")
            title = title_node.text().strip() if title_node else ""
            page_count = 0
            for node in parser.css("a, iframe, embed, object"):
                href = node.attributes.get("href") or node.attributes.get("src") or node.attributes.get("data")
                if not href:
                    continue
                target, _ = urldefrag(urljoin(final_url, href))
                if target.startswith("http://"):
                    target = "https://" + target[7:]
                if urlparse(target).scheme not in {"http", "https"}:
                    continue
                anchor = node.text().strip()
                if self.is_pdf_url(target):
                    documents.add(target)
                    page_count += 1
                    inferred = infer_metadata(target, anchor_text=anchor,
                        breadcrumb=crumbs + [title, final_url], scheme_hint=source.get("scheme_hint", "s2023"))
                    inferred["discovery_evidence"] = {"original_page_url": url, "final_page_url": final_url,
                        "source_id": source["id"], "retrieved_at": datetime.now(timezone.utc).isoformat(), "mode": mode}
                    association = {"source_id": source["id"], "source_page_url": url,
                                   "final_page_url": final_url, "anchor_text": anchor}
                    inferred["discovery_associations"] = [association]
                    existing = session.execute(sa.select(DiscoveredLink).where(DiscoveredLink.url == target)).scalar_one_or_none()
                    if existing is None:
                        session.add(DiscoveredLink(url=target, source_page_id=page.id, anchor_text=anchor,
                            breadcrumb=crumbs + [title], inferred=inferred, link_status="new"))
                        outcome.new_links += 1
                    else:
                        # Confirmed manual corrections must survive rediscovery.
                        previous = existing.inferred or {}
                        associations = list(previous.get("discovery_associations", []))
                        if association not in associations:
                            associations.append(association)
                        existing.inferred = {**inferred, **previous, "discovery_associations": associations}
                elif depth < max_depth and target not in seen:
                    iframe = node.tag in {"iframe", "embed", "object"}
                    if iframe or any(pattern.search(target) for pattern in patterns):
                        seen.add(target)
                        queue.append((target, depth + 1, crumbs + [title or anchor], page.id))
            page.link_count = page_count
            if not page_count and depth == 0 and not queue:
                page.last_error = "NO_DOCUMENT_LINKS"
            session.commit()
        outcome.documents_found = len(documents)
        if queue:
            outcome.failures.append({"url": seed, "reason": f"PAGE_LIMIT_REACHED:{max_pages}"})
