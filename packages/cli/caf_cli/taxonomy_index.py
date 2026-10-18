"""Build read-only taxonomy reconciliation drafts from module contents pages."""

import json
from pathlib import Path

import typer

from caf_l0.index_parser import build_index_report
from caf_l0.manifest import load_manifest

app = typer.Typer(help="Extract module contents as evidence-backed taxonomy review drafts")


@app.command("draft")
def draft(
    manifest: Path = typer.Option(Path("taxonomy/textbook_v1/manifest.json"), exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", "-o", help="New JSON review report; existing files are preserved"),
    base_path: Path = typer.Option(Path("."), help="Root for artifact local_path values"),
    pdf_page: list[int] | None = typer.Option(None, "--pdf-page", help="Explicit 1-based index PDF page; repeat as needed. Applies to each front-matter source."),
) -> None:
    """Extract and compare contents without changing the manifest or database."""
    if output.exists():
        raise typer.BadParameter("Output already exists; choose a new report path", param_hint="--output")
    try:
        report = build_index_report(load_manifest(manifest), base_path, pdf_page)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    entries = sum(len(source.get("entries", [])) for source in report["sources"])
    typer.echo(f"Wrote {entries} draft index entries from {len(report['sources'])} front-matter sources to {output}")
