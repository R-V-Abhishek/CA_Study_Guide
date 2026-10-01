"""Read-only corpus provenance reports."""

from pathlib import Path
import json

from rich.console import Console
import typer

from caf_common.audit import collect_baseline, write_baseline
from caf_common.settings import get_settings
from caf_db.engine import get_engine

app = typer.Typer(help="Read-only provenance and corpus audits")
console = Console()


@app.command("baseline")
def baseline(
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Audit root; creates a unique timestamped child directory"),
    checkpoint_manifest: Path | None = typer.Option(None, "--checkpoint-manifest", help="Compare protected content with a captured recovery manifest"),
) -> None:
    """Report corpus provenance without changing the source database."""
    settings = get_settings()
    engine = get_engine()
    try:
        report = collect_baseline(engine)
        if checkpoint_manifest:
            manifest = json.loads(checkpoint_manifest.read_text())
            expected = {table: content for table, content in manifest["tables"].items()
                        if table.startswith(("app.", "core."))}
            actual = report["protected_table_content"]
            mismatches = sorted(table for table in expected.keys() | actual.keys()
                                if expected.get(table) != actual.get(table))
            report["checkpoint_comparison"] = {"manifest": str(checkpoint_manifest),
                                                "unchanged": not mismatches, "mismatches": mismatches}
        folder = write_baseline(report, output_dir or settings.storage.data_dir / "audits")
    finally:
        engine.dispose()
    console.print(f"Provenance baseline: {folder / 'baseline.md'}")
    console.print(f"Machine-readable evidence: {folder / 'baseline.json'}")
    for category, count in report["provenance_category_counts"].items():
        console.print(f"  {category}: {count}")
    if checkpoint_manifest:
        console.print(f"Protected checkpoint content unchanged: {not mismatches}")
        if mismatches:
            raise typer.Exit(code=1)
