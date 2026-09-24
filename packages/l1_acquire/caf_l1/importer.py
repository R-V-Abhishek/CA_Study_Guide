"""L1 manual document importer."""

from pathlib import Path
import tomllib
from typing import Any
import fitz
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.blob_store import BlobStore
from caf_common.logging import get_logger
from caf_l1.infer import infer_metadata
from caf_db.models.ingest import Document

logger = get_logger("acquire.importer")


class ManualImporter:
    def __init__(self, blob_store: BlobStore) -> None:
        self.blob_store = blob_store

    def import_file(
        self,
        pdf_path: Path,
        session: Session,
        run_id: int | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> Document:
        if not pdf_path.exists() or not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        data = pdf_path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ValueError(f"File {pdf_path.name} is not a valid PDF")

        # PyMuPDF check
        doc = fitz.open(stream=data, filetype="pdf")
        page_count = len(doc)
        has_text = any(len(p.get_text()) > 20 for p in doc)
        doc.close()

        # Compute hash and store in content-addressed storage
        sha256_hash, blob_path = self.blob_store.put(data)

        # Check sidecar meta.toml
        meta_path = pdf_path.with_suffix(".meta.toml")
        sidecar_meta = {}
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                sidecar_meta = tomllib.load(f)

        # Fallback to inferred from filename
        inferred = infer_metadata(pdf_path.name)

        # Merge: sidecar > overrides > inferred
        meta = {**inferred, **(overrides or {}), **sidecar_meta}

        scheme_id = meta.get("scheme_id", "s2023")
        attempt_id = meta.get("attempt_id")
        paper_id = meta.get("paper_id")
        doc_type_id = meta.get("doc_type_id")
        series = meta.get("series")
        title = meta.get("title") or pdf_path.stem
        catalog_status = "inferred" if (attempt_id and paper_id and doc_type_id) else "needs_curation"

        existing = session.execute(
            sa.select(Document).where(Document.sha256 == sha256_hash)
        ).scalar_one_or_none()

        if existing:
            logger.info("document_already_exists", sha256=sha256_hash, id=existing.id)
            return existing

        new_doc = Document(
            sha256=sha256_hash,
            blob_path=str(blob_path),
            bytes=len(data),
            origin="manual",
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
        session.commit()
        session.refresh(new_doc)

        logger.info("imported_document", id=new_doc.id, sha256=sha256_hash, title=title)
        return new_doc

    def import_directory(
        self,
        inbox_dir: Path,
        session: Session,
        run_id: int | None = None,
    ) -> list[Document]:
        imported = []
        for pdf in sorted(inbox_dir.glob("*.pdf")):
            try:
                doc = self.import_file(pdf, session, run_id=run_id)
                imported.append(doc)
            except Exception as exc:
                logger.error("import_error", file=pdf.name, error=str(exc))
        return imported
