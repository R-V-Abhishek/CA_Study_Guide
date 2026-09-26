"""L1 link discovery module."""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urldefrag
import httpx
from selectolax.parser import HTMLParser
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.logging import get_logger
from caf_l1.infer import infer_metadata
from caf_l1.robots import PolitenessManager
from caf_db.models.ingest import DiscoveredLink, SourcePage
from caf_db.models.ops import Event, Run

logger = get_logger("acquire.discover")


def _upgrade_redirect(response: httpx.Response) -> None:
    if response.is_redirect:
        loc = response.headers.get("location", "")
        if loc.startswith("http://"):
            response.headers["location"] = "https://" + loc[7:]


class LinkDiscoverer:
    def __init__(
        self,
        sources: list[dict[str, Any]],
        politeness: PolitenessManager,
    ) -> None:
        self.sources = sources
        self.politeness = politeness

    def is_pdf_url(self, url: str) -> bool:
        clean = url.split("?")[0].lower()
        return clean.endswith(".pdf") or "cdn.icai.org" in clean

    def discover_source(
        self,
        source: dict[str, Any],
        session: Session,
        run_id: int | None = None,
    ) -> int:
        source_id = source["id"]
        seed_url = source["url"]
        if seed_url.startswith("http://"):
            seed_url = "https://" + seed_url[7:]
        mode = source.get("mode", "http")
        max_depth = source.get("max_depth", 2)
        follow_patterns = [re.compile(p) for p in source.get("follow_patterns", [])]
        scheme_hint = source.get("scheme_hint", "s2023")

        logger.info("discover_source_start", source_id=source_id, url=seed_url, mode=mode)

        if mode == "browser":
            logger.info("browser_mode_deferred_to_assisted", source_id=source_id)
            return 0

        queue: list[tuple[str, int, list[str], int | None]] = [(seed_url, 0, [], None)]
        seen_urls: set[str] = {seed_url}
        discovered_count = 0

        headers = {"User-Agent": self.politeness.user_agent}

        with httpx.Client(
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
            event_hooks={"response": [_upgrade_redirect]},
        ) as client:
            while queue:
                current_url, depth, crumbs, parent_page_id = queue.pop(0)
                if current_url.startswith("http://"):
                    current_url = "https://" + current_url[7:]

                # Robots check
                allowed = self.politeness.is_allowed(current_url)
                if not allowed:
                    logger.warning("robots_disallowed", url=current_url)
                    if run_id:
                        session.add(
                            Event(
                                run_id=run_id,
                                level="warn",
                                code="L1_ROBOTS_ASSISTED",
                                message=f"Path disallowed by robots.txt: {current_url}",
                            )
                        )
                    continue

                self.politeness.sleep_before_request(current_url)

                # Fetch page
                try:
                    resp = client.get(current_url)
                    http_status = resp.status_code
                    html_text = resp.text if http_status == 200 else ""
                except Exception as exc:
                    logger.error("page_fetch_error", url=current_url, error=str(exc))
                    continue

                parser = HTMLParser(html_text)
                page_title = parser.css_first("title").text().strip() if parser.css_first("title") else ""

                # Record source_page
                source_page = session.execute(
                    sa.select(SourcePage).where(SourcePage.url == current_url)
                ).scalar_one_or_none()
                if not source_page:
                    source_page = SourcePage(
                        source_id=source_id,
                        url=current_url,
                        depth=depth,
                        parent_page_id=parent_page_id,
                        fetch_mode=mode,
                        robots_allowed=allowed,
                        last_fetched_at=datetime.now(timezone.utc),
                        http_status=http_status,
                        link_count=0,
                    )
                    session.add(source_page)
                    session.flush()
                else:
                    source_page.last_fetched_at = datetime.now(timezone.utc)
                    source_page.http_status = http_status

                page_pdf_count = 0

                # Scan links
                for a_tag in parser.css("a"):
                    href = a_tag.attributes.get("href")
                    if not href:
                        continue

                    abs_url = urljoin(current_url, href)
                    abs_url, _ = urldefrag(abs_url)
                    if abs_url.startswith("http://"):
                        abs_url = "https://" + abs_url[7:]
                    anchor_text = a_tag.text().strip()

                    if self.is_pdf_url(abs_url):
                        page_pdf_count += 1
                        inferred = infer_metadata(
                            abs_url,
                            anchor_text=anchor_text,
                            breadcrumb=crumbs + [page_title, current_url],
                            scheme_hint=scheme_hint,
                        )

                        existing_link = session.execute(
                            sa.select(DiscoveredLink).where(DiscoveredLink.url == abs_url)
                        ).scalar_one_or_none()

                        if not existing_link:
                            link_row = DiscoveredLink(
                                url=abs_url,
                                source_page_id=source_page.id,
                                anchor_text=anchor_text,
                                breadcrumb=crumbs + [page_title],
                                inferred=inferred,
                                link_status="new",
                            )
                            session.add(link_row)
                            discovered_count += 1
                        else:
                            existing_link.inferred = inferred

                    elif depth < max_depth and abs_url not in seen_urls:
                        # Check if matching follow patterns
                        should_follow = any(pat.search(abs_url) for pat in follow_patterns)
                        if should_follow:
                            seen_urls.add(abs_url)
                            queue.append((abs_url, depth + 1, crumbs + [page_title or anchor_text], source_page.id))

                source_page.link_count = page_pdf_count
                session.commit()

        logger.info("discover_source_finish", source_id=source_id, discovered=discovered_count)
        return discovered_count
