"""L1 polite document downloader and blob store integrator."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from caf_common.db_safety import assert_acquisition_allowed
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.blob_store import BlobStore
from caf_common.logging import get_logger
from caf_l1.robots import PolitenessManager
from caf_l1.artifacts import record_observation, validate_metadata, validate_pdf
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
        self.last_report: dict = {}

    def fetch_pending(
        self,
        session: Session,
        limit: int = 50,
        run_id: int | None = None,
        link_ids: list[int] | None = None,
        refetch: bool = False,
    ) -> int:
        assert_acquisition_allowed()
        if limit < 1:
            raise ValueError("limit must be positive")
        now = datetime.now(timezone.utc)
        self.last_report = {"attempted": 0, "downloaded": 0, "failures": [], "associations": []}

        # Select pending links, prioritizing inferred exam paper links
        query = sa.select(DiscoveredLink)
        if link_ids is not None:
            query = query.where(DiscoveredLink.id.in_(link_ids))
        links = session.execute(
            query
            .where(
                DiscoveredLink.link_status.in_(["new", "failed", "downloaded"] if refetch else ["new", "failed"]),
                sa.or_(DiscoveredLink.next_try_at.is_(None), DiscoveredLink.next_try_at <= now),
                sa.true() if refetch else DiscoveredLink.tries < 3,
            )
            .order_by(
                DiscoveredLink.inferred["paper_id"].is_not(None).desc(),
                DiscoveredLink.id.desc(),
            )
            .limit(limit)
        ).scalars().all()

        downloaded_count = 0

        for link in links:
            self.last_report["attempted"] += 1
            url = link.url
            if url.startswith("http://"):
                url = "https://" + url[7:]
            logger.info("fetching_document", url=url, tries=link.tries)
            self.politeness.sleep_before_request(url)
            attempt_number = link.tries + 1
            link.tries = attempt_number
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

                try:
                    verified = validate_pdf(content)
                    inferred = validate_metadata(link.inferred or {}, verified)
                except ValueError as exc:
                    link.link_status = "not_pdf" if str(exc) == "MISSING_PDF_HEADER" else "failed"
                    link.last_error = str(exc)
                    session.commit()
                    continue

                # Store in content-addressed blob store
                sha256_hash, blob_path = self.blob_store.put(content)

                # Metadata
                previous_doc = session.get(Document, link.document_id) if link.document_id else None
                receipt = record_observation(self.blob_store, sha256_hash, origin="http", original_url=link.url,
                    final_url=str(resp.url), metadata=inferred,
                    response={"status": resp.status_code, "content_type": resp.headers.get("content-type"),
                              "etag": resp.headers.get("etag"), "last_modified": resp.headers.get("last-modified"),
                              "bytes": len(content)}, previous_digest=previous_doc.sha256 if previous_doc else None)
                inferred["latest_acquisition_receipt"] = str(receipt.relative_to(self.blob_store.base_dir))
                link.inferred = inferred
                scheme_id = inferred.get("scheme_id", "s2023")
                attempt_id = inferred.get("attempt_id")
                paper_id = inferred.get("paper_id")
                doc_type_id = inferred.get("doc_type_id")
                series = inferred.get("series")
                title = inferred.get("title") or link.anchor_text or Path(url).name
                catalog_status = inferred.get("catalog_status", "needs_curation")

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
                        course_level=inferred.get("course_level"),
                        provenance_status="unresolved",
                        scheme_id=scheme_id,
                        attempt_id=attempt_id,
                        paper_id=paper_id,
                        doc_type_id=doc_type_id,
                        series=series,
                        collection_id=inferred.get("collection_id"),
                        paper_page_ranges=inferred.get("paper_page_ranges") or [],
                        metadata_evidence=inferred.get("metadata_evidence") or {},
                        title=title,
                        catalog_status=catalog_status,
                        extract_status="pending",
                        page_count=verified.page_count,
                        has_text_layer=verified.has_text_layer,
                        created_run_id=run_id,
                        supersedes_document_id=previous_doc.id if previous_doc and previous_doc.sha256 != sha256_hash else None,
                    )
                    session.add(new_doc)
                    session.flush()

                    link.document_id = new_doc.id
                    link.link_status = "downloaded"
                    downloaded_count += 1

                link.last_error = None
                link.next_try_at = None
                self.last_report["associations"].append({"link_id": link.id, "document_id": link.document_id,
                                                        "sha256": sha256_hash})
                session.commit()

            except Exception as exc:
                session.rollback()
                logger.error("fetch_exception", url=url, error=str(exc))
                link.tries = attempt_number
                link.last_error = str(exc)
                link.next_try_at = now + timedelta(seconds=60)
                if link.tries >= 3:
                    link.link_status = "failed"
                session.commit()

        self.last_report["downloaded"] = downloaded_count
        self.last_report["failures"] = [{"link_id": link.id, "url": link.url, "status": link.link_status,
                                         "reason": link.last_error} for link in links if link.last_error]

        return downloaded_count
