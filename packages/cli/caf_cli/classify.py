"""CLI commands for L3 classification."""

from typing import Annotated
from rich.console import Console
from rich.table import Table
import typer
from sqlalchemy import func, select

from caf_common.run_context import open_run
from caf_db.engine import get_session_factory
from caf_db.models.ingest import TagSuggestion, Unit
from caf_l3.pipeline import ClassificationPipeline

app = typer.Typer(name="classify", help="L3 Classification commands")
console = Console()


@app.command("run")
def classify_run(
    doc_id: Annotated[int | None, typer.Option("--doc", help="Filter by document ID")] = None,
    paper_id: Annotated[str | None, typer.Option("--paper", help="Filter by paper ID (e.g. s2023.P1)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum units to classify")] = 500,
    shadow: Annotated[bool, typer.Option("--shadow", help="Write shadow suggestions")] = False,
) -> None:
    """Run L3 classification cascade on pending gradable units."""
    session_factory = get_session_factory()
    with session_factory() as session:
        pipeline = ClassificationPipeline(session)

        console.print(f"[bold green]Running classification (limit={limit}, shadow={shadow})...[/bold green]")
        with open_run(stage="l3_classify", args={"doc_id": doc_id, "paper_id": paper_id, "limit": limit}) as run:
            summary = pipeline.run_classification(
                run_id=run.id,
                doc_id=doc_id,
                paper_id=paper_id,
                limit=limit,
                is_shadow=shadow,
            )

            table = Table(title="Classification Run Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="green", justify="right")

            table.add_row("Total Units Processed", str(summary.total_processed))
            table.add_row("Primary Suggestions", str(summary.primary_suggestions))
            table.add_row("Secondary Suggestions", str(summary.secondary_suggestions))
            for b_name in ["A", "B", "C", "D"]:
                table.add_row(f"Bucket {b_name}", str(summary.buckets.get(b_name, 0)))

            console.print(table)


@app.command("report")
def classify_report() -> None:
    """Display statistics and bucket distribution of tag suggestions."""
    session_factory = get_session_factory()
    with session_factory() as session:
        counts = (
            session.query(TagSuggestion.bucket, func.count(TagSuggestion.id))
            .filter(TagSuggestion.role == "primary", TagSuggestion.is_shadow.is_(False))
            .group_by(TagSuggestion.bucket)
            .all()
        )

        table = Table(title="L3 Tag Suggestions Bucket Distribution")
        table.add_column("Bucket", style="bold")
        table.add_column("Description", style="cyan")
        table.add_column("Count", justify="right", style="green")

        desc_map = {
            "A": "Consensus + Anchor Consistent",
            "B": "Consensus + Anchor Conflicting",
            "C": "Resolved by Tie-Break",
            "D": "No Consensus / Gap",
        }

        total = sum(c for _, c in counts)
        for b_name in ["A", "B", "C", "D"]:
            c_val = next((cnt for b, cnt in counts if b == b_name), 0)
            pct = f"({c_val / total * 100:.1f}%)" if total > 0 else ""
            table.add_row(b_name, desc_map.get(b_name, ""), f"{c_val} {pct}")

        console.print(table)
        console.print(f"[bold]Total Primary Suggestions:[/bold] {total}")


@app.command("evaluate")
def classify_evaluate(
    threshold: Annotated[float, typer.Option("--threshold", "-t", help="Minimum Bucket A precision threshold (0.0 - 1.0)")] = 0.80,
    min_samples: Annotated[int, typer.Option("--min-samples", "-m", help="Minimum evaluated samples for strict gating")] = 5,
) -> None:
    """Evaluate classifier suggestions against human curator decisions in core.decision."""
    from caf_l3.evaluate import evaluate_model_on_reviewed_decisions

    session_factory = get_session_factory()
    with session_factory() as session:
        console.print(f"[bold cyan]Evaluating classification models against reviewed decisions (Bucket A threshold: {threshold * 100:.0f}%)...[/bold cyan]")
        report = evaluate_model_on_reviewed_decisions(
            session=session,
            bucket_a_threshold=threshold,
            min_samples=min_samples,
        )

        table = Table(title="Model Evaluation per Confidence Bucket", show_header=True)
        table.add_column("Bucket", style="bold")
        table.add_column("Total Samples", justify="right")
        table.add_column("Human Agreed", justify="right", style="green")
        table.add_column("Precision", justify="right", style="magenta")

        for b in ["A", "B", "C", "D"]:
            metric = report.bucket_metrics.get(b)
            if metric and metric.total > 0:
                table.add_row(
                    b,
                    str(metric.total),
                    str(metric.matched),
                    f"{metric.precision * 100:.1f}%",
                )
            else:
                table.add_row(b, "0", "0", "N/A")

        console.print(table)
        console.print(f"Total Reviewed Decisions Evaluated: [bold]{report.total_reviewed}[/bold]")
        console.print(f"Top-1 Agreement: [bold cyan]{report.top1_agreement * 100:.1f}%[/bold cyan]")

        gate_style = "bold green" if report.passed else "bold red"
        console.print(f"\nGate Outcome: [{gate_style}]{'PASSED' if report.passed else 'FAILED'}[/{gate_style}]")
        console.print(f"[dim]{report.status_note}[/dim]")

        if not report.passed:
            raise typer.Exit(code=1)

