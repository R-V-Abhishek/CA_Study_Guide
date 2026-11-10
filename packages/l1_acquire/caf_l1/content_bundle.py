"""Verified content snapshots: source PDFs, catalogue hints and acquisition evidence by SHA-256.

A snapshot carries sources only. Extraction, classification and every human decision are made
again on the importing database, so no internal row ID crosses between installations.
"""

from calendar import month_name
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import tomllib
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa
from sqlalchemy.orm import Session

from caf_common.blob_store import BlobStore
from caf_db.models.extraction import DocumentPair
from caf_db.models.ingest import Document
from caf_db.models.ref import Attempt, DocType, Paper, Scheme
from caf_l1.artifacts import validate_metadata, validate_pdf
from caf_l1.importer import new_document

SHA256 = r"^[0-9a-f]{64}$"
CATALOG_FIELDS = (
    "course_level",
    "scheme_id",
    "attempt_id",
    "paper_id",
    "doc_type_id",
    "series",
    "part",
    "title",
    "collection_id",
    "paper_page_ranges",
)
MAX_PDF_BYTES = 200 * 1024**2
MAX_JSON_BYTES = 1024**2


class ContentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=SHA256)
    bytes: int = Field(gt=0, le=MAX_PDF_BYTES)
    origin: Literal["http", "browser", "assisted", "manual"]
    catalog: dict[str, Any]
    supersedes_sha256: str | None = Field(default=None, pattern=SHA256)
    answer_sha256s: list[str] = []
    # Observation member name -> SHA-256 of its exact bytes.
    observations: dict[str, str]


class ContentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[1] = 1
    snapshot_id: str = Field(pattern=SHA256)
    entries: list[ContentEntry] = Field(min_length=1)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def snapshot_id(entries: list[ContentEntry]) -> str:
    return hashlib.sha256(canonical([entry.model_dump() for entry in entries])).hexdigest()


def pdf_hosts(path: Path = Path("config/sources.toml")) -> set[str]:
    return set(tomllib.loads(path.read_text())["defaults"]["pdf_hosts"])


def official_observation(observation: dict, sha256: str, hosts: set[str]) -> bool:
    """Provenance is verified only by an HTTPS download of these exact bytes from an approved host."""
    url = urlparse(observation.get("final_url") or "")
    return (
        observation.get("sha256") == sha256
        and observation.get("origin") in {"http", "browser"}
        and url.scheme == "https"
        and url.hostname in hosts
    )


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _member(name: str, data: bytes) -> tuple[tarfile.TarInfo, io.BytesIO]:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), 0, 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info, io.BytesIO(data)


def build_bundle(
    session: Session, blob_store: BlobStore, sha256s: list[str], output_dir: Path
) -> Path:
    """Write a deterministic bundle of official sources; the same inputs give the same bytes."""
    if not sha256s or len(sha256s) != len(set(sha256s)):
        raise ValueError("Select each document SHA-256 once")
    hosts = pdf_hosts()
    documents = {
        d.sha256: d
        for d in session.scalars(sa.select(Document).where(Document.sha256.in_(sha256s)))
    }
    if missing := sorted(set(sha256s) - set(documents)):
        raise ValueError(f"Unknown documents: {', '.join(missing)}")
    by_id = {d.id: d for d in documents.values()}
    pairs = session.scalars(
        sa.select(DocumentPair).where(
            DocumentPair.question_document_id.in_(list(by_id)), DocumentPair.status == "confirmed"
        )
    ).all()
    answers: dict[int, list[str]] = {}
    for pair in pairs:
        answer = session.get(Document, pair.answer_document_id)
        answers.setdefault(pair.question_document_id, []).append(answer.sha256)
    entries, members = [], {}
    for sha in sorted(sha256s):
        document = documents[sha]
        if document.catalog_status == "rejected":
            raise ValueError(f"Rejected document cannot be published: {sha}")
        data = blob_store.read(sha)
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f"Stored blob does not match its SHA-256: {sha}")
        folder = blob_store.base_dir / "acquisition" / sha[:2] / sha
        observations = {}
        official = False
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            raw = path.read_bytes()
            official |= official_observation(json.loads(raw), sha, hosts)
            name = f"observations/{sha}/{path.name}"
            observations[name] = hashlib.sha256(raw).hexdigest()
            members[name] = raw
        if not official:
            raise ValueError(f"No HTTPS acquisition evidence from an approved host: {sha}")
        predecessor = (
            session.get(Document, document.supersedes_document_id)
            if document.supersedes_document_id
            else None
        )
        entries.append(
            ContentEntry(
                sha256=sha,
                bytes=len(data),
                origin=document.origin,
                catalog={field: getattr(document, field) for field in CATALOG_FIELDS},
                supersedes_sha256=predecessor.sha256 if predecessor else None,
                answer_sha256s=sorted(answers.get(document.id, [])),
                observations=observations,
            )
        )
        members[f"sources/{sha}.pdf"] = data
    manifest = ContentManifest(snapshot_id=snapshot_id(entries), entries=entries)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = output_dir / f"content-{manifest.snapshot_id[:12]}.tar.gz"
    if bundle.exists():
        raise FileExistsError(f"Bundle already exists: {bundle}")
    members["manifest.json"] = manifest.model_dump_json(indent=2).encode() + b"\n"
    partial = bundle.with_name(bundle.name + ".partial")
    # gzip's header holds a timestamp; mtime=0 keeps the archive bytes reproducible.
    with (
        partial.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name in sorted(members):
            archive.addfile(*_member(name, members[name]))
    partial.replace(bundle)
    bundle.with_name(bundle.name + ".sha256").write_text(f"{file_digest(bundle)}  {bundle.name}\n")
    verify_bundle(bundle)
    return bundle


def verify_bundle(bundle: Path) -> ContentManifest:
    """Stream members without extraction; reject links, paths, extras, duplicates and corruption."""
    expected = bundle.with_name(bundle.name + ".sha256").read_text()
    if expected != f"{file_digest(bundle)}  {bundle.name}\n":
        raise ValueError("Outer bundle SHA-256 mismatch")
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate bundle members")
        if any(not member.isfile() for member in members):
            raise ValueError("Bundle must contain regular files only")
        if "manifest.json" not in names or archive.getmember("manifest.json").size > MAX_JSON_BYTES:
            raise ValueError("Missing or oversized manifest")
        manifest = ContentManifest.model_validate_json(archive.extractfile("manifest.json").read())
        if manifest.snapshot_id != snapshot_id(manifest.entries):
            raise ValueError("Snapshot identity does not match its entries")
        shas = [entry.sha256 for entry in manifest.entries]
        if shas != sorted(set(shas)):
            raise ValueError("Entries must be unique and sorted by SHA-256")
        declared = {"manifest.json"}
        for entry in manifest.entries:
            source = f"sources/{entry.sha256}.pdf"
            if any(
                not re.fullmatch(rf"observations/{entry.sha256}/[0-9A-Za-z_-]+\.json", name)
                for name in entry.observations
            ):
                raise ValueError(f"Invalid observation member name for {entry.sha256}")
            declared |= {source, *entry.observations}
        if set(names) != declared:
            raise ValueError("Unexpected or missing bundle members")
        for entry in manifest.entries:
            source = archive.getmember(f"sources/{entry.sha256}.pdf")
            if source.size != entry.bytes:
                raise ValueError(f"Source size mismatch: {entry.sha256}")
            data = archive.extractfile(source).read()
            if hashlib.sha256(data).hexdigest() != entry.sha256:
                raise ValueError(f"Source SHA-256 mismatch: {entry.sha256}")
            validate_pdf(data)
            for name, digest in entry.observations.items():
                member = archive.getmember(name)
                if member.size > MAX_JSON_BYTES:
                    raise ValueError(f"Oversized observation: {name}")
                raw = archive.extractfile(member).read()
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError(f"Observation SHA-256 mismatch: {name}")
                if json.loads(raw).get("sha256") != entry.sha256:
                    raise ValueError(f"Observation describes other bytes: {name}")
    return manifest


def import_bundle(session: Session, blob_store: BlobStore, bundle: Path, run_id: int) -> dict:
    """Add a verified snapshot in the caller's transaction. Existing documents are never changed."""
    manifest = verify_bundle(bundle)
    hosts = pdf_hosts()
    session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext('caf.content_import'))"))
    catalogs = [entry.catalog for entry in manifest.entries]
    for model, field in ((Scheme, "scheme_id"), (Paper, "paper_id"), (DocType, "doc_type_id")):
        values = {c[field] for c in catalogs if c.get(field)}
        if model is Paper:
            values |= {r["paper_id"] for c in catalogs for r in c.get("paper_page_ranges") or []}
        known = set(session.scalars(sa.select(model.id).where(model.id.in_(values))))
        if unknown := sorted(values - known):
            raise ValueError(f"Unknown {field} values: {', '.join(unknown)}")
    created_attempts = []
    for attempt_id in sorted({c["attempt_id"] for c in catalogs if c.get("attempt_id")}):
        if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", attempt_id):
            raise ValueError(f"Invalid attempt_id: {attempt_id}")
        if session.get(Attempt, attempt_id) is None:
            year, month = map(int, attempt_id.split("-"))
            # Like corpus acquisition, a source attempt is recorded unverified until reviewed.
            session.add(
                Attempt(
                    id=attempt_id,
                    exam_year=year,
                    exam_month=month,
                    label=f"{month_name[month]} {year}",
                    verified=False,
                )
            )
            created_attempts.append(attempt_id)
    session.flush()
    imported, existing = [], []
    documents = {}
    with tarfile.open(bundle, "r:gz") as archive:
        for entry in manifest.entries:
            observations = {
                name: archive.extractfile(name).read() for name in sorted(entry.observations)
            }
            folder = blob_store.base_dir / "acquisition" / entry.sha256[:2] / entry.sha256
            for name, raw in observations.items():
                target = folder / Path(name).name
                if not target.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(".tmp")
                    temporary.write_bytes(raw)
                    temporary.replace(target)
            current = session.scalar(sa.select(Document).where(Document.sha256 == entry.sha256))
            if current is not None:
                differs = sorted(
                    field
                    for field in CATALOG_FIELDS
                    if field != "title" and getattr(current, field) != entry.catalog.get(field)
                )
                existing.append({"sha256": entry.sha256, "id": current.id, "differs": differs})
                documents[entry.sha256] = current
                continue
            data = archive.extractfile(f"sources/{entry.sha256}.pdf").read()
            verified = validate_pdf(data)
            stored, blob_path = blob_store.put(data)
            if stored != entry.sha256:
                raise ValueError(f"Stored source changed during import: {entry.sha256}")
            meta = validate_metadata(dict(entry.catalog), verified)
            meta["metadata_evidence"]["content_snapshot"] = {
                "snapshot_id": manifest.snapshot_id,
                "answer_sha256s": entry.answer_sha256s,
                "observations": sorted(Path(name).name for name in entry.observations),
            }
            official = any(
                official_observation(json.loads(raw), entry.sha256, hosts)
                for raw in observations.values()
            )
            document = new_document(
                entry.sha256,
                blob_path,
                len(data),
                verified,
                meta,
                origin=entry.origin,
                provenance_status="verified" if official else "unresolved",
                run_id=run_id,
            )
            session.add(document)
            documents[entry.sha256] = document
            imported.append(
                {
                    "sha256": entry.sha256,
                    "catalog_status": document.catalog_status,
                    "provenance_status": document.provenance_status,
                }
            )
    session.flush()
    for entry in manifest.entries:
        if entry.supersedes_sha256 is None:
            continue
        document = documents[entry.sha256]
        predecessor = documents.get(entry.supersedes_sha256) or session.scalar(
            sa.select(Document).where(Document.sha256 == entry.supersedes_sha256)
        )
        if predecessor is None:
            raise ValueError(f"Superseded source is not installed: {entry.supersedes_sha256}")
        if document.supersedes_document_id is None and document.id not in {
            row["id"] for row in existing
        }:
            document.supersedes_document_id = predecessor.id
    for row in imported:
        row["id"] = documents[row["sha256"]].id
    session.flush()
    return {
        "snapshot_id": manifest.snapshot_id,
        "imported": imported,
        "existing": existing,
        "created_attempts": created_attempts,
    }
