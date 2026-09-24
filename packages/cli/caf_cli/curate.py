"""CLI commands for L4 curation."""

from typing import Annotated
from rich.console import Console
from rich.table import Table
import typer
from sqlalchemy import func, select

from caf_common.run_context import open_run
from caf_db.engine import get_session_factory
from caf_db.models.core import Appearance, AppearanceTag, Decision
from caf_db.models.ingest import Document, TagSuggestion, Unit
from caf_l4.publish import bulk_accept_bucket_a

app = typer.Typer(name="curate", help="L4 Curation commands")
console = Console()


@app.command("queue")
def curate_queue(
    paper_id: Annotated[str | None, typer.Option("--paper", help="Filter by paper ID")] = None,
    bucket: Annotated[str | None, typer.Option("--bucket", help="Filter by bucket (A, B, C, D)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max units to list")] = 20,
) -> None:
    """List pending units in the human review queue."""
    session_factory = get_session_factory()
    with session_factory() as session:
        query = (
            select(Unit, Document)
            .join(Document, Unit.document_id == Document.id)
            .where(
                Unit.current.is_(True),
                Unit.is_gradable.is_(True),
                Unit.classify_status == "suggested",
            )
        )
        if paper_id:
            query = query.where(Document.paper_id == paper_id)

        rows = session.execute(query.limit(limit * 2)).all()
        table = Table(title="Curator Review Queue")
        table.add_column("Unit ID", style="cyan")
        table.add_column("Paper / Attempt", style="magenta")
        table.add_column("Label")
        table.add_column("Marks", justify="right")
        table.add_column("Bucket", style="bold")
        table.add_column("Primary Node", style="green")

        count = 0
        for u, doc in rows:
            suggs = (
                session.query(TagSuggestion)
                .filter(TagSuggestion.unit_id == u.id, TagSuggestion.is_shadow.is_(False))
                .all()
            )
            prim = next((s for s in suggs if s.role == "primary"), None)
            if not prim:
                continue
            if bucket and prim.bucket != bucket:
                continue

            b_style = {
                "A": "[green]A[/green]",
                "B": "[yellow]B[/yellow]",
                "C": "[cyan]C[/cyan]",
                "D": "[red]D[/red]",
            }.get(prim.bucket, prim.bucket)

            table.add_row(
                str(u.id),
                f"{doc.paper_id or '—'} {doc.attempt_id or '—'}",
                u.display_label,
                str(u.marks or "—"),
                b_style,
                prim.node_id,
            )
            count += 1
            if count >= limit:
                break

        console.print(table)
        console.print(f"[bold]Showing {count} unit(s).[/bold]")


@app.command("bulk-accept")
def curate_bulk_accept(
    doc_id: Annotated[int, typer.Option("--doc", help="Document ID whose Bucket A units to publish")] = ...,
) -> None:
    """Bulk accept all remaining Bucket A suggestions for a confirmed document."""
    session_factory = get_session_factory()
    with session_factory() as session:
        with open_run(stage="l4_bulk_accept", args={"doc_id": doc_id}) as run:
            count = bulk_accept_bucket_a(session, doc_id)
            console.print(f"[bold green]Successfully bulk-accepted and published {count} Bucket A units for document {doc_id}.[/bold green]")


@app.command("stats")
def curate_stats() -> None:
    """Display overall knowledge store statistics and curation progress."""
    session_factory = get_session_factory()
    with session_factory() as session:
        pub_appearances = session.query(func.count(Appearance.id)).filter(Appearance.status == "published").scalar() or 0
        pub_tags = session.query(func.count(AppearanceTag.appearance_id)).scalar() or 0
        decisions_count = session.query(func.count(Decision.id)).scalar() or 0
        pending_review = (
            session.query(func.count(Unit.id))
            .filter(Unit.current.is_(True), Unit.is_gradable.is_(True), Unit.classify_status == "suggested")
            .scalar() or 0
        )

        table = Table(title="Knowledge Store Curation Progress")
        table.add_column("Entity", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("Published Appearances (core.appearance)", str(pub_appearances))
        table.add_row("Published Appearance Tags (core.appearance_tag)", str(pub_tags))
        table.add_row("Human Decisions (core.decision)", str(decisions_count))
        table.add_row("Pending Units in Review Queue", str(pending_review))

        console.print(table)
