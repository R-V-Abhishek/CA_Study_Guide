"""Export independent OpenRouter classifications for student Markdown review."""

import json
from pathlib import Path

import httpx
import sqlalchemy as sa
import typer

from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.extraction import ExtractionRevision
from caf_db.models.ingest import Document
from caf_l3.batches import export_batch, validate_manifest
from caf_l2.revisions import digest
from caf_l3.openrouter import DEFAULT_MODEL, free_models, load_results, review_manifest, run_review
from caf_l3.review_markdown import render_review_markdown

app = typer.Typer(help="Independent AI classification files for student review; never updates the queue")


@app.command("luna-status")
def luna_status(root: Path = typer.Option(Path("data/student_review/luna-papers"), "--root")) -> None:
    """Show actual saved coverage after correcting paper assignments."""
    from caf_l3.corpus_review import corpus_status
    typer.echo(json.dumps(corpus_status(root), indent=2))


@app.command("luna-render")
def luna_render(
    markdown: Path = typer.Option(..., "--markdown"),
    root: Path = typer.Option(Path("data/student_review/luna-papers"), "--root"),
    allow_pending: bool = typer.Option(False, "--allow-pending", help="Explicit interim pack with missing classifications marked"),
) -> None:
    """Combine all corrected paper packs into one Markdown file without duplicates."""
    from caf_l3.corpus_review import render_corpus
    try:
        status = render_corpus(root, markdown, allow_pending=allow_pending)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(f"Wrote {markdown}; {status['saved']}/{status['total']} roots have AI proposals")


def new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


@app.command("models")
def models() -> None:
    """List currently free schema-capable models, newest first (not an accuracy ranking)."""
    try:
        with httpx.Client(timeout=30) as client:
            available = free_models(client)
    except httpx.HTTPError as exc:
        typer.echo(f"OpenRouter catalog unavailable ({type(exc).__name__}); check network access and retry. No model calls made.", err=True)
        raise typer.Exit(1) from None
    except ValueError:
        typer.echo("OpenRouter catalog response could not be validated. No model calls made.", err=True)
        raise typer.Exit(1) from None
    for model in available:
        typer.echo(f"{model.id}\t{model.context_length} context\tcreated {model.created}")


@app.command("export")
def export(
    output: Path = typer.Option(..., "--output", "-o"),
    taxonomy: str = typer.Option("textbook-v1", "--taxonomy"),
    model: str = typer.Option(DEFAULT_MODEL, "--model"),
    revision: list[int] | None = typer.Option(None, "--revision", help="Repeat; defaults to latest available extraction per document"),
    paper: str | None = typer.Option(None, "--paper"),
    batch_source: Path | None = typer.Option(None, "--batch-source", exists=True,
        help="Reuse a frozen export instead of querying the database"),
    draft: bool = typer.Option(True, "--draft/--reviewed-only", help="Student evaluation may include unapproved evidence, marked experimental"),
) -> None:
    """Freeze all selected complete roots/parts/answers and candidate evidence, read-only."""
    if output.exists():
        raise typer.BadParameter("Output already exists; use a new path")
    if batch_source:
        batch = json.loads(batch_source.read_text())
        validate_manifest(batch)
        if paper or revision:
            raise typer.BadParameter("Paper/revision filters require a database export")
    else:
        with get_session_factory("operations")() as session:
            # Nothing in this command commits or changes extraction/classification state.
            if revision is None:
                if draft:
                    # The corpus has candidate extractions awaiting review. Include
                    # them explicitly for student evaluation without promoting them.
                    latest = sa.select(sa.func.max(ExtractionRevision.id).label("id")).where(
                        ExtractionRevision.status != "failed").group_by(ExtractionRevision.document_id).subquery()
                    query = sa.select(ExtractionRevision.id).join(latest,
                        latest.c.id == ExtractionRevision.id).join(Document,
                        Document.id == ExtractionRevision.document_id).where(
                        Document.catalog_status != "rejected")
                else:
                    query = sa.select(ExtractionRevision.id).join(Document,
                        Document.current_revision_id == ExtractionRevision.id).where(
                        Document.catalog_status == "confirmed")
                query = query.where(Document.superseded.is_(False), Document.course_level == "final",
                    Document.provenance_status == "verified", ExtractionRevision.status != "failed").order_by(ExtractionRevision.id)
                if paper:
                    query = query.where(Document.paper_id == paper)
                revision = list(session.scalars(query))
            batch = export_batch(session, taxonomy, revision, draft=draft, model=model)
            if paper:
                batch["records"] = [record for record in batch["records"] if record["context"]["paper_id"] == paper]
                if not batch["records"]:
                    raise typer.BadParameter("No gradable questions match the selected paper")
                batch["batch_key"] = digest({k: v for k, v in batch.items() if k != "batch_key"})
    frozen = review_manifest(batch, model)
    new_json(output, frozen)
    typer.echo(f"Exported {len(frozen['records'])} complete roots; no queue or database changes")


@app.command("render")
def render(
    batch: Path = typer.Option(..., "--batch", exists=True),
    results: Path = typer.Option(..., "--results"),
    markdown: Path = typer.Option(..., "--markdown"),
) -> None:
    """Render all roots, including visibly missing or failed AI results."""
    manifest = json.loads(batch.read_text())
    validate_manifest(manifest)
    state_path = results / "review-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and state["batch_key"] != manifest["batch_key"]:
        raise typer.BadParameter("Results state belongs to another batch")
    if markdown.exists():
        raise typer.BadParameter("Markdown already exists; preserve student edits and choose a new path")
    text = render_review_markdown(manifest, load_results(manifest, results), state.get("failures", {}))
    markdown.parent.mkdir(parents=True, exist_ok=True)
    with markdown.open("x") as handle:
        handle.write(text)
    typer.echo(f"Wrote {markdown}")


@app.command("run")
def run(
    batch: Path = typer.Option(..., "--batch", exists=True),
    results: Path = typer.Option(..., "--results"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximum NEW roots; saved results are resumed"),
) -> None:
    """Obtain free-only AI outputs into local files; never import them into the queue."""
    manifest = json.loads(batch.read_text())
    key = get_settings().OPENROUTER_API_KEY
    if key is None:
        raise typer.BadParameter("OPENROUTER_API_KEY is not configured")
    try:
        state = run_review(manifest, results, key.get_secret_value(), limit=limit)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"AI completed {state['completed']}; pending {state['pending']}")
    if state["failures"]:
        for question, error in state["failures"].items():
            typer.echo(f"{question}: {error}", err=True)
        raise typer.Exit(1)
