"""CLI commands for L3 classification and calibration benchmark."""

from typing import Annotated
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer
from sqlalchemy import func, select

from caf_common.run_context import open_run
from caf_db.engine import get_session_factory
from caf_db.models.ingest import TagSuggestion, Unit
from caf_l3.benchmark import evaluate_calibration_benchmark, generate_calibration_benchmark, list_benchmark_units
from caf_l3.pipeline import ClassificationPipeline

app = typer.Typer(name="classify", help="L3 Classification commands")
console = Console()


@app.command("run")
def classify_run(
    doc_id: Annotated[int | None, typer.Option("--doc", help="Filter by document ID")] = None,
    paper_id: Annotated[str | None, typer.Option("--paper", help="Filter by paper ID (e.g. s2023.P1)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum units to classify")] = 100,
    model: Annotated[str | None, typer.Option("--model", help="Override LLM model (e.g. gemini-2.5-flash)")] = None,
    resume: Annotated[bool, typer.Option("--resume/--no-resume", help="Skip already-suggested units")] = True,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm", help="Enable/disable Gemini LLM calls")] = True,
    shadow: Annotated[bool, typer.Option("--shadow", help="Write shadow suggestions")] = False,
) -> None:
    """Run L3 classification cascade on pending gradable units with resumability."""
    session_factory = get_session_factory()
    with session_factory() as session:
        pipeline = ClassificationPipeline(session, model_override=model)

        mode_str = f"LLM ({model or 'default'})" if (use_llm and pipeline.gemini_classifier.is_available()) else "Local Anchor/Keyword Cascade"
        console.print(f"[bold green]Running classification (limit={limit}, mode={mode_str}, resume={resume})...[/bold green]")

        with open_run(stage="l3_classify", args={"doc_id": doc_id, "paper_id": paper_id, "limit": limit, "model": model}) as run:
            summary = pipeline.run_classification(
                run_id=run.id,
                doc_id=doc_id,
                paper_id=paper_id,
                limit=limit,
                is_shadow=shadow,
                resume=resume,
                use_llm=use_llm,
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

            if summary.quota_exhausted:
                console.print(
                    Panel(
                        f"[bold yellow]⚠️ Quota Notice:[/bold yellow]\n{summary.status_message}\n\n"
                        f"All {summary.total_processed} processed units were committed safely.\n"
                        f"Run [bold cyan]uv run caf classify run --resume[/bold cyan] when quota resets.",
                        title="API Quota Exceeded",
                        border_style="yellow",
                    )
                )


@app.command("test-set")
def classify_test_set(
    generate: Annotated[bool, typer.Option("--generate", "-g", help="Generate a new stratified benchmark")] = False,
    size_per_paper: Annotated[int, typer.Option("--size-per-paper", "-s", help="Target samples per paper")] = 10,
    list_units: Annotated[bool, typer.Option("--list", "-l", help="List current benchmark units")] = False,
) -> None:
    """Manage the representative calibration test set across all 6 papers."""
    session_factory = get_session_factory()
    with session_factory() as session:
        if generate:
            console.print(f"[bold cyan]Generating stratified calibration benchmark ({size_per_paper} units per paper across all 6 papers)...[/bold cyan]")
            count = generate_calibration_benchmark(session, size_per_paper=size_per_paper)
            console.print(f"[bold green]✓ Successfully flagged {count} units as calibration benchmark![/bold green]")
            console.print("You can now review them in Curator UI by filtering for Calibration Set, or evaluate via:")
            console.print("  ▶ [cyan]uv run caf classify evaluate --benchmark[/cyan]\n")

        if list_units or (not generate and not list_units):
            units = list_benchmark_units(session)
            if not units:
                console.print("[yellow]No calibration benchmark units currently flagged. Run with '--generate' first.[/yellow]")
                return

            table = Table(title=f"Calibration Benchmark Units ({len(units)} total)", show_header=True)
            table.add_column("Unit ID", style="bold", justify="right")
            table.add_column("Paper", style="cyan")
            table.add_column("Attempt", style="magenta")
            table.add_column("Label", style="green")
            table.add_column("Marks", justify="right")
            table.add_column("Status")
            table.add_column("Question Preview", style="dim")

            for u in units:
                table.add_row(
                    str(u["unit_id"]),
                    u["paper_id"],
                    u["attempt_id"] or "-",
                    u["display_label"],
                    str(u["marks"] or "-"),
                    u["classify_status"],
                    u["question_preview"],
                )
            console.print(table)


@app.command("evaluate")
def classify_evaluate(
    threshold: Annotated[float, typer.Option("--threshold", "-t", help="Minimum Bucket A precision threshold (0.0 - 1.0)")] = 0.80,
    min_samples: Annotated[int, typer.Option("--min-samples", "-m", help="Minimum evaluated samples for strict gating")] = 5,
    benchmark: Annotated[bool, typer.Option("--benchmark", "-b", help="Evaluate specifically on the calibration test set")] = False,
) -> None:
    """Evaluate classifier suggestions against human curator decisions."""
    session_factory = get_session_factory()
    with session_factory() as session:
        if benchmark:
            console.print(f"[bold cyan]Evaluating AI suggestions on Calibration Benchmark (Target: {threshold * 100:.0f}%)...[/bold cyan]")
            bench_report = evaluate_calibration_benchmark(session, threshold=threshold)

            table = Table(title="Calibration Benchmark Evaluation per Paper", show_header=True)
            table.add_column("Paper", style="bold")
            table.add_column("Total Benchmark", justify="right")
            table.add_column("Reviewed", justify="right", style="cyan")
            table.add_column("Agreed", justify="right", style="green")
            table.add_column("Precision", justify="right", style="magenta")
            table.add_column("Status", justify="center")

            for p_id, p_metric in bench_report.paper_metrics.items():
                p_code = p_id.split(".")[-1]
                prec_str = f"{p_metric.precision * 100:.1f}%" if p_metric.decided > 0 else "N/A"
                stat_style = "[green]PASS[/green]" if p_metric.status == "PASSED" else ("[yellow]PENDING[/yellow]" if p_metric.status == "PENDING" else "[red]FAIL[/red]")
                table.add_row(
                    p_code,
                    str(p_metric.total),
                    str(p_metric.decided),
                    str(p_metric.matched),
                    prec_str,
                    stat_style,
                )

            console.print(table)
            console.print(f"\n[bold]Total Benchmark Samples:[/bold] {bench_report.total_samples}")
            console.print(f"[bold]Reviewed Decisions:[/bold] {bench_report.total_decided}")
            console.print(f"[bold]Overall Precision:[/bold] {bench_report.overall_precision * 100:.1f}%\n")

            if bench_report.passed:
                console.print(Panel(f"[bold green]GATE PASSED:[/bold green] {bench_report.status_note}", border_style="green"))
            else:
                console.print(Panel(f"[bold yellow]GATE PENDING/FAILED:[/bold yellow] {bench_report.status_note}", border_style="yellow"))
            return

        # General evaluation across all reviewed decisions
        from caf_l3.evaluate import evaluate_model_on_reviewed_decisions
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
        console.print(f"\nTotal Reviewed Decisions Evaluated: {report.total_reviewed}")
        console.print(f"Top-1 Agreement: {report.top1_agreement * 100:.1f}%\n")
        console.print(f"Gate Outcome: {'PASSED' if report.passed else 'FAILED'}")
        console.print(report.status_note)


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
            "A": "Consensus / High Confidence",
            "B": "Moderate Confidence / Multi-standard",
            "C": "Low Confidence / Tie-Break",
            "D": "Comprehensive Case Scenario",
        }

        total = sum(c for _, c in counts)
        for b_name in ["A", "B", "C", "D"]:
            c_val = next((cnt for b, cnt in counts if b == b_name), 0)
            pct = f"({c_val / total * 100:.1f}%)" if total > 0 else ""
            table.add_row(b_name, desc_map.get(b_name, ""), f"{c_val} {pct}")

        console.print(table)
        console.print(f"[bold]Total Primary Suggestions:[/bold] {total}")
