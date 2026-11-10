"""Content snapshots: build on the curating machine, verify anywhere, import into an installation."""

import json
from pathlib import Path
from typing import Annotated

import typer

from caf_common.blob_store import BlobStore
from caf_common.run_context import open_run
from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_l1.content_bundle import build_bundle, import_bundle, verify_bundle

app = typer.Typer(name="content", help="Verified source-content snapshots")


@app.command("build")
def content_build(
    output_dir: Annotated[Path, typer.Option("--output-dir")],
    sha256s: Annotated[
        list[str] | None, typer.Option("--sha", help="Document SHA-256; repeat")
    ] = None,
    from_file: Annotated[
        Path | None, typer.Option("--from-file", help="File with one document SHA-256 per line")
    ] = None,
) -> None:
    """Package official source PDFs with their catalogue hints and acquisition evidence."""
    selected = list(sha256s or [])
    if from_file:
        selected += [line.strip() for line in from_file.read_text().splitlines() if line.strip()]
    store = BlobStore(get_settings().storage.blob_dir)
    with get_session_factory("operations")() as session:
        bundle = build_bundle(session, store, selected, output_dir)
    typer.echo(
        json.dumps({"bundle": str(bundle), "snapshot_id": verify_bundle(bundle).snapshot_id})
    )


@app.command("verify")
def content_verify(bundle: Path) -> None:
    """Check every checksum and source without touching a database or storage."""
    manifest = verify_bundle(bundle)
    typer.echo(
        json.dumps({"snapshot_id": manifest.snapshot_id, "documents": len(manifest.entries)})
    )


@app.command("import")
def content_import(bundle: Path) -> None:
    """Add a verified snapshot in one transaction; documents await administrator confirmation."""
    manifest = verify_bundle(bundle)
    store = BlobStore(get_settings().storage.blob_dir)
    with open_run("content.import", {"snapshot_id": manifest.snapshot_id}) as run:
        with get_session_factory("operations")() as session:
            summary = import_bundle(session, store, bundle, run.id)
            session.commit()
        run.stats = {
            "imported": len(summary["imported"]),
            "existing": len(summary["existing"]),
            "created_attempts": summary["created_attempts"],
        }
    typer.echo(json.dumps({**summary, "run_id": run.id}))
