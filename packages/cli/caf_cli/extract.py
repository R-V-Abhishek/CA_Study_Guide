"""CLI commands for L2 extraction."""

from pathlib import Path
from typing import Annotated
from rich.console import Console
from rich.table import Table
import typer
from sqlalchemy import func, select

from caf_common.blob_store import BlobStore
from caf_common.run_context import open_run
from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_db.models.ingest import Document, Unit
from caf_l2.pipeline import ExtractionPipeline

app = typer.Typer(name="extract", help="L2 Extraction commands")
console = Console()


@app.command("run")
def extract_run(
    doc_id: Annotated[int | None, typer.Option("--doc", help="Specific document ID to extract")] = None,
    profile_path: Annotated[str | None, typer.Option("--profile", help="Path to custom profile YAML")] = None,
    status: Annotated[str, typer.Option("--status", help="Document extract_status filter")] = "pending",
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 25,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="List selection without creating revisions")] = False,
    promote: Annotated[bool, typer.Option("--promote", help="Explicitly promote candidates after parsing")] = False,
    ocr: Annotated[bool, typer.Option("--ocr", help="Enable configured Tesseract worker for raster pages")] = False,
) -> None:
    """Run L2 extraction pipeline on confirmed documents."""
    settings = get_settings()
    session_factory = get_session_factory("operations")
    blob_store = BlobStore(settings.storage.blob_dir)

    profiles_dir = Path("profiles")
    overrides_dir = Path("overrides")
    debug_dir = Path("data/debug")

    from caf_l2.blocks import OCRConfig
    pipeline = ExtractionPipeline(
        blob_store=blob_store,
        profiles_dir=profiles_dir,
        overrides_dir=overrides_dir,
        debug_dir=debug_dir,
        ocr_config=OCRConfig(language=settings.ocr.language,dpi=settings.ocr.dpi,
            min_native_chars=settings.ocr.min_native_chars,tessdata=settings.ocr.tessdata) if ocr or settings.ocr.enabled else None,
    )

    with session_factory() as session:
        # Find candidate documents
        query = select(Document).where(
            Document.catalog_status == "confirmed",
            Document.superseded.is_(False),
        )
        if doc_id is not None:
            query = query.where(Document.id == doc_id)
        else:
            query = query.where(Document.extract_status == status, Document.course_level == 'final',
                Document.provenance_status == 'verified', Document.scheme_id == 's2023')

        docs = session.scalars(query.order_by(Document.id).limit(limit)).all()
        if not docs:
            console.print(f"[yellow]No documents found matching criteria (doc_id={doc_id}, status={status}).[/yellow]")
            return

        if dry_run:
            for doc in docs:
                console.print(f"{doc.id}: {doc.course_level}/{doc.scheme_id}/{doc.paper_id} {doc.attempt_id or doc.collection_id} {doc.doc_type_id}; current revision={doc.current_revision_id}")
            return

        console.print(f"[bold green]Starting extraction on {len(docs)} document(s)...[/bold green]")

        with open_run(stage="l2_extract", args={"doc_id": doc_id, "status": status}) as run:
            table = Table(title="Extraction Results")
            table.add_column("Doc ID", style="cyan")
            table.add_column("Attempt / Paper", style="magenta")
            table.add_column("Status", style="bold")
            table.add_column("Pages", justify="right")
            table.add_column("Units", justify="right")
            table.add_column("Gradables", justify="right")
            table.add_column("Issues", style="red")

            failures = []
            for doc in docs:
                p_override = Path(profile_path) if profile_path else None
                try:
                    summary = pipeline.extract_document(
                        session=session,
                        document_id=doc.id,
                        run_id=run.id,
                        profile_override_path=p_override,
                        promote=promote,
                    )
                    status_style = {
                        "ok": "[green]OK[/green]",
                        "ok_with_warnings": "[yellow]WARN[/yellow]",
                        "needs_review": "[red]NEEDS_REVIEW[/red]",
                    }.get(summary.extract_status, summary.extract_status)

                    issues_str = ", ".join(i["code"] for i in summary.validation_issues[:3])
                    if len(summary.validation_issues) > 3:
                        issues_str += f" (+{len(summary.validation_issues) - 3} more)"

                    table.add_row(
                        str(doc.id),
                        f"{doc.attempt_id or '—'} {doc.paper_id or '—'}",
                        status_style,
                        str(summary.page_count),
                        str(summary.total_units),
                        str(summary.gradable_units),
                        issues_str or "—",
                    )
                    console.print(f"Document {doc.id}: revision {summary.revision_id} ({summary.revision_status})")
                    if summary.extract_status == "needs_review":
                        failures.append(doc.id)
                except Exception as e:
                    failures.append(doc.id)
                    table.add_row(
                        str(doc.id),
                        f"{doc.attempt_id or '—'} {doc.paper_id or '—'}",
                        "[bold red]FAILED[/bold red]",
                        "—",
                        "—",
                        "—",
                        str(e),
                    )

            console.print(table)
            if failures:
                run.stats = {**run.stats, "failed_or_needs_review": failures}
                raise typer.Exit(1)


@app.command("compare")
def compare_revision(revision_id: int) -> None:
    """Print exact content reconciliation before promoting a candidate."""
    from caf_db.models.extraction import ReconciliationLink
    with get_session_factory("operations")() as session:
        rows = session.scalars(select(ReconciliationLink).where(ReconciliationLink.revision_id == revision_id).order_by(ReconciliationLink.id))
        for row in rows:
            console.print(f"{row.relation}: old unit={row.old_unit_id} new={row.new_label}; {row.evidence}")


@app.command("promote")
def promote_candidate(revision_id: int, expected_current: int | None = None) -> None:
    """Transactionally promote a candidate with an explicit current-revision check."""
    from caf_l2.revisions import promote_revision
    with get_session_factory("operations")() as session:
        try:
            result = promote_revision(session, revision_id, expected_current)
            session.commit()
            console.print(result)
        except ValueError as exc:
            session.rollback()
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc


@app.command("debug")
def extract_debug(
    doc_id: Annotated[int, typer.Option("--doc", help="Document ID to inspect and render")] = ...,
) -> None:
    """Generate interactive debug HTML showing line blocks and unit segmentation."""
    settings = get_settings()
    session_factory = get_session_factory("operations")
    blob_store = BlobStore(settings.storage.blob_dir)

    profiles_dir = Path("profiles")
    overrides_dir = Path("overrides")
    debug_dir = Path("data/debug")

    pipeline = ExtractionPipeline(
        blob_store=blob_store,
        profiles_dir=profiles_dir,
        overrides_dir=overrides_dir,
        debug_dir=debug_dir,
    )

    with session_factory() as session:
        doc = session.get(Document, doc_id)
        if not doc:
            console.print(f"[bold red]Document {doc_id} not found.[/bold red]")
            return

        with open_run(stage="l2_extract_debug", args={"doc_id": doc_id}) as run:
            summary = pipeline.extract_document(
                session=session,
                document_id=doc.id,
                run_id=run.id,
            )
            console.print(f"[bold green]Debug render generated successfully![/bold green]")
            console.print(f"Outcome: [bold]{summary.extract_status}[/bold]")
            console.print(f"Total units: {summary.total_units} (Gradables: {summary.gradable_units})")
            if summary.debug_html_path:
                console.print(f"HTML: [cyan]{summary.debug_html_path}[/cyan]")


@app.command("report")
def extract_report() -> None:
    """Display summary of extracted documents and validation statistics."""
    session_factory = get_session_factory("operations")
    with session_factory() as session:
        # Document extract status counts
        doc_stats = (
            session.query(Document.extract_status, func.count(Document.id))
            .filter(Document.catalog_status == "confirmed")
            .group_by(Document.extract_status)
            .all()
        )

        table = Table(title="Document Extraction Status")
        table.add_column("Extract Status", style="cyan")
        table.add_column("Count", justify="right")
        for st, count in doc_stats:
            table.add_row(st, str(count))
        console.print(table)

        # Unit count
        unit_count = session.query(func.count(Unit.id)).filter(Unit.current.is_(True)).scalar() or 0
        gradable_count = (
            session.query(func.count(Unit.id))
            .filter(Unit.current.is_(True), Unit.is_gradable.is_(True))
            .scalar() or 0
        )
        console.print(f"\n[bold]Current Units:[/bold] {unit_count} total, {gradable_count} gradable.")
