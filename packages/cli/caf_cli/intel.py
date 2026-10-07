"""CLI commands for L5 Intelligence and scoring."""

from rich.console import Console
from rich.table import Table
import typer

from caf_db.engine import get_session_factory
from caf_db.models.intel import IngestionCoverage, ScoreRun, SubtopicScore
from caf_db.models.ref import Attempt, Node, Paper
from caf_l5 import (
    compute_weighted_coverage,
    get_current_score_run,
    get_subtopic_scores_for_paper,
    get_subtopic_why,
    get_weak_subtopics,
    is_subtopic_weak,
    recompute_scores,
)

app = typer.Typer(help="L5 Intelligence & Scoring commands")
console = Console()


@app.command("recompute")
def cmd_recompute(
    target_attempt: str = typer.Option(
        ..., "--target-attempt", "-t", help="Target attempt ID (e.g. 2024-11 or 2026-05)"
    ),
    shadow: bool = typer.Option(
        False, "--shadow", help="Run in shadow mode (do not make current)"
    ),
) -> None:
    """Enqueue durable recomputation; publication remains immediately readable."""
    from caf_l5.jobs import enqueue_recompute
    with get_session_factory("operations")() as session:
        if shadow:
            run = recompute_scores(session, target_attempt_id=target_attempt, shadow=True)
            console.print(f"Shadow run {run.id}: {run.status}")
        else:
            job = enqueue_recompute(session, target_attempt)
            console.print(f"Queued job {job.id}: {job.status}, generation {job.corpus_generation}")


@app.command("enqueue")
def cmd_enqueue(target_attempt: str = typer.Option(..., "--target-attempt"),
                taxonomy_version: int | None = typer.Option(None, "--taxonomy-version")) -> None:
    from caf_l5.jobs import enqueue_recompute
    with get_session_factory("operations")() as session:
        job = enqueue_recompute(session, target_attempt, taxonomy_version)
        console.print(f"Queued job {job.id}: {job.status}, generation {job.corpus_generation}")


@app.command("worker")
def cmd_worker(once: bool = typer.Option(False, "--once"),
               owner_token: str | None = typer.Option(None, "--owner-token", hidden=True)) -> None:
    from caf_l5.jobs import run_worker_once
    if once:
        job = run_worker_once(get_session_factory("operations"))
        console.print(f"Completed job {job}" if job else "Queue is idle")
    else:
        from caf_l5.worker import main
        main()


@app.command("status")
def cmd_status(target_attempt: str = typer.Option(..., "--target-attempt"),
               taxonomy_version: int | None = typer.Option(None, "--taxonomy-version")) -> None:
    from caf_l5.jobs import job_status
    with get_session_factory("operations")() as session:
        console.print(job_status(session, target_attempt, taxonomy_version))


@app.command("report")
def cmd_report(
    target_attempt: str = typer.Option(..., "--target-attempt"),
    taxonomy_version: int | None = typer.Option(None, "--taxonomy-version"),
    paper: str = typer.Option("P1", "--paper", "-p", help="Paper code (e.g. P1, P2)"),
    top: int = typer.Option(15, "--top", "-n", help="Number of top subtopics to show"),
) -> None:
    """Display intelligence report for a paper showing top topics by Importance score."""
    session_factory = get_session_factory("operations")
    with session_factory() as session:
        # Resolve paper
        p_row = session.query(Paper).where(
            (Paper.code == paper.upper()) | (Paper.id == paper)
        ).first()
        if not p_row:
            console.print(f"[bold red]Paper '{paper}' not found.[/bold red]")
            raise typer.Exit(code=1)

        current_run = get_current_score_run(session, target_attempt, taxonomy_version)
        if current_run:
            taxonomy_version = current_run.taxonomy_version_id
        if not current_run:
            console.print("[bold red]No current score run found. Run 'caf intel recompute' first.[/bold red]")
            raise typer.Exit(code=1)

        scores_map = get_subtopic_scores_for_paper(session, p_row.id, current_run.id, target_attempt_id=target_attempt, taxonomy_version_id=taxonomy_version)
        if not scores_map:
            console.print(f"No scores found for paper {p_row.code}.")
            return

        nodes = session.query(Node).where(Node.paper_id == p_row.id).all()
        node_names = {n.id: n.name for n in nodes}

        # Sort by importance descending
        sorted_scores = sorted(
            scores_map.values(), key=lambda s: s.importance if s.importance is not None else -1, reverse=True
        )[:top]

        table = Table(
            title=f"Paper {p_row.code} ({p_row.name}) — Top Subtopics by Importance (Run #{current_run.id}, Target {current_run.target_attempt_id})"
        )
        table.add_column("Node ID", style="cyan", no_wrap=True)
        table.add_column("Subtopic Name", style="bold")
        table.add_column("Importance (I)", style="bold magenta", justify="right")
        table.add_column("Exam (E)", justify="right")
        table.add_column("Practice (P)", justify="right")
        table.add_column("Weight (W)", justify="right")
        table.add_column("Freq (F/N)", justify="center")
        table.add_column("Marks", justify="right")
        table.add_column("Exams", justify="right")
        table.add_column("Weak?", justify="center")

        for s in sorted_scores:
            weak = is_subtopic_weak(s.applicable, s.freq_hits, s.freq_window, "not_started")
            weak_str = "[bold red]YES[/bold red]" if weak else "-"
            table.add_row(
                s.node_id,
                node_names.get(s.node_id, s.node_id)[:38],
                f"{s.importance:.4f}" if s.importance is not None else "unavailable",
                f"{s.exam_score:.2f}" if s.exam_score is not None else "unavailable",
                f"{s.practice_score:.2f}" if s.practice_score is not None else "unavailable",
                f"{s.weight_prior:.2f}" if s.weight_prior is not None else "unavailable",
                f"{s.freq_hits}/{s.freq_window}",
                str(s.exam_marks_total),
                str(s.exam_count),
                weak_str,
            )

        console.print(table)


@app.command("why")
def cmd_why(node_id: str = typer.Argument(...),
            target_attempt: str = typer.Option(..., "--target-attempt"),
            taxonomy_version: int | None = typer.Option(None, "--taxonomy-version")) -> None:
    """Show persisted formula, normalized contributions and exact reviewed window."""
    import json
    from caf_l5.context import approved_binding
    from caf_l5.config import ScoringConfig, load_scoring_config
    with get_session_factory("operations")() as session:
        binding = approved_binding(session, target_attempt, taxonomy_version)
        if binding:
            taxonomy_version = binding.taxonomy_version_id
            config = ScoringConfig.model_validate(binding.scoring_config) if binding.scoring_config else load_scoring_config()
        else:
            config = load_scoring_config()
        try:
            payload = get_subtopic_why(session, node_id, target_attempt_id=target_attempt,
                                      taxonomy_version_id=taxonomy_version, config_hash=config.config_hash)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)
        if payload.get("error"):
            console.print(payload["error"])
            raise typer.Exit(code=1)
        console.print_json(json.dumps(payload))


@app.command("coverage")
def cmd_coverage(user_id: int = typer.Option(..., "--user-id", min=1, help="Target account ID")) -> None:
    """Display ingestion coverage and weighted syllabus coverage."""
    session_factory = get_session_factory("student")
    with session_factory() as session:
        cov = compute_weighted_coverage(session, user_id=user_id)
        console.print(f"\n[bold cyan]Syllabus Coverage Summary[/bold cyan]")
        console.print(f"Overall Done: [bold green]{cov['overall_coverage_pct']}%[/bold green] | In Progress: [bold yellow]{cov['overall_in_progress_pct']}%[/bold yellow]")

        for g_no, g_data in sorted(cov.get("groups", {}).items()):
            console.print(f"  Group {g_no}: Done: {g_data['coverage_pct']}% | In Progress: {g_data['in_progress_pct']}%")

        table = Table(title="Paper Coverage Breakdown")
        table.add_column("Paper Code", style="cyan")
        table.add_column("Completed Coverage %", style="bold green", justify="right")
        table.add_column("In Progress %", style="bold yellow", justify="right")

        for p_id, p_data in sorted(cov.get("papers", {}).items(), key=lambda x: x[1]["code"]):
            table.add_row(
                p_data["code"],
                f"{p_data['coverage_pct']}%",
                f"{p_data['in_progress_pct']}%",
            )
        console.print(table)


@app.command("backfill-reader")
def cmd_backfill_reader() -> None:
    """Project existing reviewed publications without creating reviews."""
    from caf_l4.questions import backfill_publications
    with get_session_factory("operations")() as session:
        result = backfill_publications(session)
        session.commit()
        console.print(result)


@app.command("seed-coverage")
def cmd_seed_coverage(taxonomy_version: int = typer.Option(..., "--taxonomy-version")) -> None:
    """Record Phase 4 inventory blockers while leaving official scope unreviewed."""
    from caf_l5.coverage import seed_coverage
    with get_session_factory("operations")() as session:
        console.print(seed_coverage(session, taxonomy_version))
