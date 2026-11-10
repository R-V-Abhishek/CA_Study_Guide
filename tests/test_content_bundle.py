"""Content snapshots: deterministic build, strict verification and additive, all-or-nothing import."""

import gzip
import hashlib
import io
import itertools
import json
from pathlib import Path
import tarfile

import fitz
import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from caf_common.blob_store import BlobStore
from caf_db.models.ingest import Document
from caf_db.models.ops import Run
from caf_db.models.ref import Attempt
from caf_l1.artifacts import record_observation
from caf_l1.content_bundle import (
    ContentManifest,
    build_bundle,
    import_bundle,
    snapshot_id,
    verify_bundle,
)
from caf_l1.importer import ManualImporter

OFFICIAL = "https://resource.cdn.icai.org/90001bos-final-p1.pdf"
_serial = itertools.count()


def pdf_bytes(text):
    with fitz.open() as doc:
        doc.new_page().insert_text((50, 70), text)
        return doc.tobytes()


def add_source(session, store, tmp_path, name, text, *, url=OFFICIAL, attempt="2024-05"):
    path = tmp_path / f"{name}.pdf"
    path.write_bytes(pdf_bytes(text))
    document = ManualImporter(store).import_file(
        path,
        session,
        overrides={
            "course_level": "final",
            "scheme_id": "s2023",
            "attempt_id": attempt,
            "paper_id": "s2023.P1",
            "doc_type_id": "question_paper",
        },
    )
    if url:
        record_observation(
            store,
            document.sha256,
            origin="http",
            original_url=url,
            final_url=url,
            metadata={"source": "test"},
        )
    return document


@pytest.fixture
def sources(session, tmp_path):
    store = BlobStore(tmp_path / "curating-blobs")
    session.add(
        Attempt(id="2031-11", exam_year=2031, exam_month=11, label="Nov 2031", verified=True)
    )
    session.commit()
    first = add_source(
        session, store, tmp_path, "may", "FINAL\nQUESTION PAPER\nMAY 2024\nPaper 1\n1. Leases."
    )
    second = add_source(
        session,
        store,
        tmp_path,
        "nov",
        "FINAL\nQUESTION PAPER\nNOVEMBER 2031\nPaper 1\n1. Revenue.",
        attempt="2031-11",
    )
    return store, [first.sha256, second.sha256]


def rewrite(bundle, *, manifest=None, members=None, drop=(), extra=None, link=None):
    """Repack a bundle with changes and a matching outer checksum, as an attacker could."""
    with tarfile.open(bundle, "r:gz") as archive:
        contents = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}
    if manifest:
        data = json.loads(contents["manifest.json"])
        manifest(data)
        contents["manifest.json"] = json.dumps(data).encode()
    contents.update(members or {})
    for name in drop:
        contents.pop(name)
    target = bundle.with_name(f"changed-{next(_serial)}-{bundle.name}")
    with tarfile.open(target, "w:gz") as archive:
        for name, data in [*contents.items(), *(extra or [])]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo(link)
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            archive.addfile(info)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + ".sha256").write_text(f"{digest}  {target.name}\n")
    return target


def reidentify(data):
    data["snapshot_id"] = snapshot_id(ContentManifest.model_validate(data).entries)


def test_build_is_deterministic_and_requires_official_provenance(session, sources, tmp_path):
    store, shas = sources
    first = build_bundle(session, store, shas, tmp_path / "a")
    second = build_bundle(session, store, list(reversed(shas)), tmp_path / "b")
    assert first.name == second.name
    assert first.read_bytes() == second.read_bytes()
    manifest = verify_bundle(first)
    assert [entry.sha256 for entry in manifest.entries] == sorted(shas)
    assert all(len(entry.observations) == 2 for entry in manifest.entries)  # manual + http
    with pytest.raises(FileExistsError):
        build_bundle(session, store, shas, tmp_path / "a")

    manual = add_source(
        session,
        store,
        tmp_path,
        "manual",
        "FINAL\nQUESTION PAPER\nMAY 2024\nPaper 1\n2. Tax.",
        url=None,
    )
    with pytest.raises(ValueError, match="No HTTPS acquisition evidence"):
        build_bundle(session, store, [manual.sha256], tmp_path / "c")
    elsewhere = add_source(
        session,
        store,
        tmp_path,
        "mirror",
        "FINAL\nQUESTION PAPER\nMAY 2024\nPaper 1\n3. Audit.",
        url="https://mirror.example.invalid/p1.pdf",
    )
    with pytest.raises(ValueError, match="No HTTPS acquisition evidence"):
        build_bundle(session, store, [elsewhere.sha256], tmp_path / "d")
    with pytest.raises(ValueError, match="Unknown documents"):
        build_bundle(session, store, ["0" * 64], tmp_path / "e")


def test_verify_rejects_tampering_extras_links_and_identity_changes(session, sources, tmp_path):
    store, shas = sources
    bundle = build_bundle(session, store, shas, tmp_path / "out")
    source = f"sources/{shas[0]}.pdf"
    cases = [
        ("SHA-256 mismatch|size mismatch", rewrite(bundle, members={source: pdf_bytes("other")})),
        ("Unexpected or missing", rewrite(bundle, extra=[("notes.txt", b"x")])),
        ("regular files only", rewrite(bundle, link="sources/link.pdf")),
        ("Duplicate", rewrite(bundle, extra=[("manifest.json", b"{}")])),
        (
            "Snapshot identity",
            rewrite(
                bundle, manifest=lambda m: m["entries"][0]["catalog"].update(paper_id="s2023.P2")
            ),
        ),
        ("Unexpected or missing", rewrite(bundle, drop=[source])),
    ]
    for message, changed in cases:
        with pytest.raises(ValueError, match=message):
            verify_bundle(changed)
    bundle.with_name(bundle.name + ".sha256").write_text("0" * 64 + f"  {bundle.name}\n")
    with pytest.raises(ValueError, match="Outer bundle"):
        verify_bundle(bundle)


def test_import_is_additive_idempotent_and_awaits_confirmation(session, sources, tmp_path):
    store, shas = sources
    bundle = build_bundle(session, store, shas, tmp_path / "out")
    # The importing installation has never seen these sources.
    session.execute(sa.delete(Document))
    session.execute(sa.delete(Attempt).where(Attempt.id == "2031-11"))
    session.commit()
    production = BlobStore(tmp_path / "production-blobs")
    run = Run(stage="content.import", args={}, status="running", stats={})
    session.add(run)
    session.flush()

    summary = import_bundle(session, production, bundle, run.id)
    session.commit()
    assert sorted(row["sha256"] for row in summary["imported"]) == sorted(shas)
    assert summary["existing"] == [] and summary["created_attempts"] == ["2031-11"]
    documents = session.scalars(sa.select(Document).order_by(Document.sha256)).all()
    assert [d.sha256 for d in documents] == sorted(shas)
    for document in documents:
        assert document.provenance_status == "verified"
        assert document.catalog_status != "confirmed"
        assert document.origin == "manual"
        assert document.created_run_id == run.id
        assert production.read(document.sha256) == store.read(document.sha256)
        evidence = document.metadata_evidence["content_snapshot"]
        assert evidence["snapshot_id"] == summary["snapshot_id"]
        copied = production.base_dir / "acquisition" / document.sha256[:2] / document.sha256
        assert len(list(copied.glob("*.json"))) == 2
    attempt = session.get(Attempt, "2031-11")
    assert attempt.label == "November 2031" and attempt.verified is False

    documents[0].title = "Curated in production"
    session.commit()
    again = import_bundle(session, production, bundle, run.id)
    session.commit()
    assert again["imported"] == [] and len(again["existing"]) == 2
    assert session.scalar(sa.select(sa.func.count()).select_from(Document)) == 2
    assert session.get(Document, documents[0].id).title == "Curated in production"


def test_import_rolls_back_entirely_on_unknown_reference(session, sources, tmp_path):
    store, shas = sources
    bundle = build_bundle(session, store, shas, tmp_path / "out")
    session.execute(sa.delete(Document))
    session.commit()

    def unknown_paper(data):
        data["entries"][1]["catalog"]["paper_id"] = "s2023.P9"
        reidentify(data)

    changed = rewrite(bundle, manifest=unknown_paper)
    with pytest.raises(ValueError, match="Unknown paper_id values: s2023.P9"):
        import_bundle(session, BlobStore(tmp_path / "production"), changed, None)
    session.rollback()
    assert session.scalar(sa.select(sa.func.count()).select_from(Document)) == 0

    def missing_predecessor(data):
        data["entries"][0]["supersedes_sha256"] = "f" * 64
        reidentify(data)

    changed = rewrite(bundle, manifest=missing_predecessor)
    with pytest.raises(ValueError, match="Superseded source is not installed"):
        import_bundle(session, BlobStore(tmp_path / "production"), changed, None)
    session.rollback()
    assert session.scalar(sa.select(sa.func.count()).select_from(Document)) == 0


def test_cli_import_records_the_run_and_prints_the_receipt(session, sources, tmp_path):
    from caf_cli.main import app

    store, shas = sources
    bundle = build_bundle(session, store, shas, tmp_path / "out")
    session.execute(sa.delete(Document))
    session.commit()
    result = CliRunner().invoke(app, ["content", "import", str(bundle)])
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert len(receipt["imported"]) == 2
    run = session.get(Run, receipt["run_id"])
    assert run.stage == "content.import" and run.status == "ok"
    assert run.args == {"snapshot_id": receipt["snapshot_id"]}
    assert run.stats["imported"] == 2
    verified = CliRunner().invoke(app, ["content", "verify", str(bundle)])
    assert json.loads(verified.stdout) == {"snapshot_id": receipt["snapshot_id"], "documents": 2}


def test_gzip_header_carries_no_timestamp_or_name(session, sources, tmp_path):
    store, shas = sources
    bundle = build_bundle(session, store, shas, tmp_path / "out")
    header = bundle.read_bytes()[:10]
    assert header[3] & 0x08 == 0  # no FNAME field
    assert header[4:8] == b"\0\0\0\0"  # MTIME zero
    assert gzip.decompress(bundle.read_bytes())
    assert (
        Path(bundle.with_name(bundle.name + ".sha256")).read_text().endswith(f"  {bundle.name}\n")
    )
