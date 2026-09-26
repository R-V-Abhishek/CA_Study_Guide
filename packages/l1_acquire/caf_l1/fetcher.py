"""L1 polite document downloader and blob store integrator."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import fitz  # PyMuPDF
import httpx
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.blob_store import BlobStore
from caf_common.logging import get_logger
from caf_l1.robots import PolitenessManager
from caf_db.models.ingest import DiscoveredLink, Document
from caf_db.models.ops import Event

logger = get_logger("acquire.fetcher")


def _upgrade_redirect(response: httpx.Response) -> None:
    if response.is_redirect:
        loc = response.headers.get("location", "")
        if loc.startswith("http://"):
            response.headers["location"] = "https://" + loc[7:]


class DocumentFetcher:
    def __init__(
        self,
        blob_store: BlobStore,
        politeness: PolitenessManager,
    ) -> None:
        self.blob_store = blob_store
        self.politeness = politeness

    def fetch_pending(
        self,
        session: Session,
        limit: int = 50,
        run_id: int | None = None,
    ) -> int:
        now = datetime.now(timezone.utc)

        # Select pending links, prioritizing inferred exam paper links
        links = session.execute(
            sa.select(DiscoveredLink)
            .where(
                DiscoveredLink.link_status.in_(["new", "failed"]),
                sa.or_(DiscoveredLink.next_try_at.is_(None), DiscoveredLink.next_try_at <= now),
                DiscoveredLink.tries < 3,
            )
            .order_by(
                DiscoveredLink.inferred["paper_id"].is_not(None).desc(),
                DiscoveredLink.id.desc(),
            )
            .limit(limit)
        ).scalars().all()

        downloaded_count = 0

        for link in links:
            url = link.url
            if url.startswith("http://"):
                url = "https://" + url[7:]
            logger.info("fetching_document", url=url, tries=link.tries)
            self.politeness.sleep_before_request(url)
            link.tries += 1
            link.last_checked_at = now

            try:
                with httpx.Client(
                    timeout=30.0,
                    headers={"User-Agent": self.politeness.user_agent},
                    follow_redirects=True,
                    event_hooks={"response": [_upgrade_redirect]},
                ) as client:
                    resp = client.get(url)

                if resp.status_code == 404 or resp.status_code == 410:
                    link.link_status = "failed"
                    link.last_error = f"HTTP_{resp.status_code}_GONE"
                    if run_id:
                        session.add(
                            Event(run_id=run_id, level="warn", code="L1_GONE", message=f"URL is gone: {url}")
                        )
                    session.commit()
                    continue

                if resp.status_code in [403, 401]:
                    link.link_status = "manual_required"
                    link.last_error = f"HTTP_{resp.status_code}_CHALLENGE"
                    if run_id:
                        session.add(
                            Event(run_id=run_id, level="alarm", code="L1_HUMAN_CHECK", message=f"Access challenged: {url}")
                        )
                    session.commit()
                    continue

                if resp.status_code != 200:
                    link.last_error = f"HTTP_{resp.status_code}"
                    link.next_try_at = now + timedelta(seconds=2 ** link.tries * 15)
                    if link.tries >= 3:
                        link.link_status = "failed"
                    session.commit()
                    continue

                content = resp.content

                # PDF verification
                if not content.startswith(b"%PDF-"):
                    link.link_status = "not_pdf"
                    link.last_error = "MISSING_PDF_HEADER"
                    session.commit()
                    continue

                # Verify with PyMuPDF
                try:
                    pdf_doc = fitz.open(stream=content, filetype="pdf")
                    page_count = len(pdf_doc)
                    has_text = any(len(page.get_text()) > 20 for page in pdf_doc)
                    pdf_doc.close()
                except Exception as exc:
                    link.link_status = "failed"
                    link.last_error = f"CORRUPT_PDF: {exc}"
                    session.commit()
                    continue

                # Store in content-addressed blob store
                sha256_hash, blob_path = self.blob_store.put(content)

                # Metadata
                inferred = link.inferred or {}
                scheme_id = inferred.get("scheme_id", "s2023")
                attempt_id = inferred.get("attempt_id")
                paper_id = inferred.get("paper_id")
                doc_type_id = inferred.get("doc_type_id")
                series = inferred.get("series")
                title = inferred.get("title") or link.anchor_text or Path(url).name
                catalog_status = inferred.get("catalog_status", "inferred")

                # Check if document already exists
                existing_doc = session.execute(
                    sa.select(Document).where(Document.sha256 == sha256_hash)
                ).scalar_one_or_none()

                if existing_doc:
                    # Alias to existing doc
                    link.document_id = existing_doc.id
                    link.link_status = "downloaded"
                else:
                    # New document
                    new_doc = Document(
                        sha256=sha256_hash,
                        blob_path=str(blob_path),
                        bytes=len(content),
                        origin="http",
                        scheme_id=scheme_id,
                        attempt_id=attempt_id,
                        paper_id=paper_id,
                        doc_type_id=doc_type_id,
                        series=series,
                        title=title,
                        catalog_status=catalog_status,
                        extract_status="pending",
                        page_count=page_count,
                        has_text_layer=has_text,
                        created_run_id=run_id,
                    )
                    session.add(new_doc)
                    session.flush()

                    link.document_id = new_doc.id
                    link.link_status = "downloaded"
                    downloaded_count += 1

                session.commit()

            except Exception as exc:
                logger.error("fetch_exception", url=url, error=str(exc))
                link.last_error = str(exc)
                link.next_try_at = now + timedelta(seconds=60)
                if link.tries >= 3:
                    link.link_status = "failed"
                session.commit()

        return downloaded_count
