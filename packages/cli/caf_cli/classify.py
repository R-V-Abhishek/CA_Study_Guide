"""CLI commands for L3 classification and calibration benchmark."""

from typing import Annotated
import json
from pathlib import Path
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
from caf_cli.classification_review import app as classification_review_app
app.add_typer(classification_review_app, name="review")


@app.command("export")
def classify_export(
    output: Annotated[Path, typer.Option("--output")],
    taxonomy: Annotated[str, typer.Option("--taxonomy")],
    revisions: Annotated[list[int], typer.Option("--revision", help="Explicit immutable extraction revisions; repeat")],
    draft: Annotated[bool, typer.Option("--draft", help="Explicit nonpublishable experiment against unreviewed snapshots")] = False,
    model: Annotated[str, typer.Option("--model")] = "gpt-6-luna",
    questions: Annotated[Path | None, typer.Option("--questions", help="JSON list of selected root IDs")] = None,
    run_label: Annotated[str | None, typer.Option("--run-label", help="Explicit new experiment identity for an intentional same-config rerun")] = None,
) -> None:
    """Export pinned complete roots, parts, answers and candidate evidence."""
    from caf_l3.batches import export_batch
    with get_session_factory("operations")() as session:
        manifest = export_batch(session, taxonomy, revisions, draft=draft, model=model,
            question_ids=json.loads(questions.read_text()) if questions else None, run_label=run_label)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    console.print(f"Exported {len(manifest['records'])} roots; batch {manifest['batch_key']}; experimental={draft}")


@app.command("operator-run")
def classify_operator_run(
    batch: Annotated[Path, typer.Option("--batch")],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
    timeout: Annotated[int, typer.Option("--timeout", min=1)] = 300,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    workers: Annotated[int, typer.Option("--workers", min=1, max=4, help="Bounded independent root jobs")] = 1,
) -> None:
    """Run Codex subscription jobs outside the web path; resume completed roots."""
    from caf_l3.batches import run_operator_batch
    state = run_operator_batch(json.loads(batch.read_text()), output_dir, timeout=timeout, limit=limit, workers=workers)
    console.print(f"Completed roots: {len(state['completed'])}; pending roots: {len(state['pending'])}; failure history: {len(state['failures'])}")
    if state['execution_failed']:
        console.print(state["failures"][-1]["error"])
        raise typer.Exit(1)


@app.command("import")
def classify_import(
    batch: Annotated[Path, typer.Option("--batch")],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
    sample: Annotated[Path | None, typer.Option("--sample", help="Frozen sampling/split metadata for benchmark display")] = None,
) -> None:
    """Validate completed outputs and append immutable suggestions idempotently."""
    from caf_l3.batches import import_batch
    manifest = json.loads(batch.read_text())
    results = []
    for record in manifest["records"]:
        path = output_dir / (record["question_id"] + ".json")
        if path.exists():
            saved = json.loads(path.read_text())
            results.append({**saved["result"], "execution": saved["execution"]})
    with open_run(stage="l3_classify_import", args={"batch_key": manifest["batch_key"]}) as run:
        with get_session_factory("operations")() as session:
            count = import_batch(session, manifest, results, run.id,
                sample=json.loads(sample.read_text()) if sample else None)
            session.commit()
        run.taxonomy_version_id = manifest["taxonomy_version_id"]
        run.stats = {"imported": count, "completed": len(results), "expected": len(manifest["records"])}
    console.print(f"Imported {count} new suggestions from {len(results)} completed roots")


@app.command("run")
def classify_run(
    taxonomy: Annotated[str | None, typer.Option("--taxonomy", help="Rebuilt textbook release ID; defaults to active release")] = None,
    doc_id: Annotated[int | None, typer.Option("--doc", help="Filter by document ID")] = None,
    paper_id: Annotated[str | None, typer.Option("--paper", help="Filter by paper ID (e.g. s2023.P1)")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum units to classify")] = 100,
    model: Annotated[str | None, typer.Option("--model", help="Override LLM model (e.g. gemini-2.5-flash)")] = None,
    resume: Annotated[bool, typer.Option("--resume/--no-resume", help="Skip already-suggested units")] = True,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-llm", help="Enable/disable Gemini LLM calls")] = True,
    shadow: Annotated[bool, typer.Option("--shadow", help="Write shadow suggestions")] = False,
) -> None:
    """Run L3 classification cascade on pending gradable units with resumability."""
    session_factory = get_session_factory("operations")
    with session_factory() as session:
        pipeline = ClassificationPipeline(session, model_override=model, version_id=taxonomy)

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
            table.add_row("Failed Units", str(summary.failed_units))
            for b_name in ["A", "B", "C", "D"]:
                table.add_row(f"Bucket {b_name}", str(summary.buckets.get(b_name, 0)))

            console.print(table)
            run.taxonomy_version_id = pipeline.classifier.taxonomy_version_id
            run.stats = {"processed": summary.total_processed, "failed": summary.failed_units,
                "buckets": summary.buckets, "primary_suggestions": summary.primary_suggestions,
                "secondary_suggestions": summary.secondary_suggestions, "is_partial": summary.is_partial}

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
            if summary.is_partial:
                raise RuntimeError(summary.status_message)


@app.command("test-set")
def classify_test_set(
    generate: Annotated[bool, typer.Option("--generate", "-g", help="Generate a new stratified benchmark")] = False,
    size_per_paper: Annotated[int, typer.Option("--size-per-paper", "-s", help="Target samples per paper")] = 10,
    list_units: Annotated[bool, typer.Option("--list", "-l", help="List current benchmark units")] = False,
) -> None:
    """Manage the representative calibration test set across all 6 papers."""
    session_factory = get_session_factory("operations")
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
    taxonomy: Annotated[str | None, typer.Option("--taxonomy", help="Taxonomy version to evaluate; defaults to active release")] = None,
    threshold: Annotated[float, typer.Option("--threshold", "-t", help="Minimum Bucket A precision threshold (0.0 - 1.0)")] = 0.80,
    min_samples: Annotated[int, typer.Option("--min-samples", "-m", help="Minimum independently adjudicated Bucket A samples")] = 30,
    benchmark: Annotated[bool, typer.Option("--benchmark", "-b", help="Evaluate specifically on the calibration test set")] = False,
) -> None:
    """Evaluate classifier suggestions against human curator decisions."""
    session_factory = get_session_factory("operations")
    with session_factory() as session:
        if benchmark:
            console.print(f"[bold cyan]Evaluating AI suggestions on Calibration Benchmark (Target: {threshold * 100:.0f}%)...[/bold cyan]")
            bench_report = evaluate_calibration_benchmark(session, threshold=threshold, version_id=taxonomy)

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
            version_id=taxonomy,
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
    session_factory = get_session_factory("operations")
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
