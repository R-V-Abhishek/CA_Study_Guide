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
    target_attempt: str | None = typer.Option(
        None, "--target-attempt", "-t", help="Target attempt ID (e.g. 2024-11 or 2026-05)"
    ),
    shadow: bool = typer.Option(
        False, "--shadow", help="Run in shadow mode (do not make current)"
    ),
) -> None:
    """Recompute all intelligence scores (E, P, W, I, F) and ingestion coverage."""
    session_factory = get_session_factory()
    with session_factory() as session:
        console.print(f"[bold cyan]Starting L5 Score Recomputation...[/bold cyan]")
        try:
            run = recompute_scores(
                session, target_attempt_id=target_attempt, shadow=shadow
            )
            console.print(
                f"[bold green]✓ Recompute successful![/bold green] "
                f"Run ID: [cyan]{run.id}[/cyan], "
                f"Target Attempt: [bold]{run.target_attempt_id}[/bold], "
                f"Version: [magenta]{run.scoring_version}[/magenta], "
                f"Is Current: [bold]{run.is_current}[/bold]"
            )

            # Quick summary table
            scores_count = (
                session.query(SubtopicScore)
                .where(SubtopicScore.score_run_id == run.id)
                .count()
            )
            cov_count = (
                session.query(IngestionCoverage)
                .where(
                    IngestionCoverage.score_run_id == run.id,
                    IngestionCoverage.exam_published.is_(True),
                )
                .count()
            )
            console.print(
                f"Scored Subtopics: [bold]{scores_count}[/bold] | "
                f"Published Exam Coverages: [bold]{cov_count}[/bold]"
            )
        except Exception as exc:
            console.print(f"[bold red]Recomputation failed:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command("report")
def cmd_report(
    paper: str = typer.Option("P1", "--paper", "-p", help="Paper code (e.g. P1, P2)"),
    top: int = typer.Option(15, "--top", "-n", help="Number of top subtopics to show"),
) -> None:
    """Display intelligence report for a paper showing top topics by Importance score."""
    session_factory = get_session_factory()
    with session_factory() as session:
        # Resolve paper
        p_row = session.query(Paper).where(
            (Paper.code == paper.upper()) | (Paper.id == paper)
        ).first()
        if not p_row:
            console.print(f"[bold red]Paper '{paper}' not found.[/bold red]")
            raise typer.Exit(code=1)

        current_run = get_current_score_run(session)
        if not current_run:
            console.print("[bold red]No current score run found. Run 'caf intel recompute' first.[/bold red]")
            raise typer.Exit(code=1)

        scores_map = get_subtopic_scores_for_paper(session, p_row.id, current_run.id)
        if not scores_map:
            console.print(f"No scores found for paper {p_row.code}.")
            return

        nodes = session.query(Node).where(Node.paper_id == p_row.id).all()
        node_names = {n.id: n.name for n in nodes}

        # Sort by importance descending
        sorted_scores = sorted(
            scores_map.values(), key=lambda s: s.importance, reverse=True
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
                f"{s.importance:.4f}",
                f"{s.exam_score:.2f}",
                f"{s.practice_score:.2f}",
                f"{s.weight_prior:.2f}",
                f"{s.freq_hits}/{s.freq_window}",
                str(s.exam_marks_total),
                str(s.exam_count),
                weak_str,
            )

        console.print(table)


@app.command("why")
def cmd_why(
    node_id: str = typer.Argument(..., help="Subtopic Node ID (e.g. P1-GDH25Q)"),
) -> None:
    """Show detailed mathematical explainability breakdown for a subtopic score."""
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            payload = get_subtopic_why(session, node_id)
        except ValueError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)

        if "error" in payload:
            console.print(f"[bold red]{payload['error']}[/bold red]")
            raise typer.Exit(code=1)

        sub = payload["subtopic"]
        breakdown = payload["importance_breakdown"]
        freq = payload["frequency"]

        console.print(f"\n[bold cyan]Explainability Breakdown for {sub['id']}[/bold cyan]")
        console.print(f"Name: [bold]{sub['name']}[/bold]")
        if sub.get("paper"):
            console.print(f"Paper: {sub['paper']['code']} - {sub['paper']['name']}")
        if sub.get("chapter"):
            console.print(f"Chapter: {sub['chapter']['name']}")

        # Importance table
        table = Table(title="Importance Calculation: I = 0.6·Ê + 0.2·P̂ + 0.2·Ŵ")
        table.add_column("Component", style="bold")
        table.add_column("Raw Score", justify="right")
        table.add_column("Paper Max", justify="right")
        table.add_column("Normalized (Hat)", justify="right")
        table.add_column("Weight", justify="right")
        table.add_column("Contribution", style="bold green", justify="right")

        table.add_row(
            "Exam (E)",
            f"{breakdown['exam']['score_E']:.4f}",
            f"{breakdown['exam']['paper_max_E']:.4f}",
            f"{breakdown['exam']['normalized_E_hat']:.4f}",
            f"{breakdown['weights']['exam']:.2f}",
            f"{breakdown['exam']['weighted_contribution']:.4f}",
        )
        table.add_row(
            "Practice (P)",
            f"{breakdown['practice']['score_P']:.4f}",
            f"{breakdown['practice']['paper_max_P']:.4f}",
            f"{breakdown['practice']['normalized_P_hat']:.4f}",
            f"{breakdown['weights']['practice']:.2f}",
            f"{breakdown['practice']['weighted_contribution']:.4f}",
        )
        table.add_row(
            "Weight Prior (W)",
            f"{breakdown['weightage_prior']['weight_prior_W']:.4f}",
            f"{breakdown['weightage_prior']['paper_max_W']:.4f}",
            f"{breakdown['weightage_prior']['normalized_W_hat']:.4f}",
            f"{breakdown['weights']['prior']:.2f}",
            f"{breakdown['weightage_prior']['weighted_contribution']:.4f}",
        )
        table.add_row(
            "[bold]Total Importance (I)[/bold]",
            "-",
            "-",
            "-",
            "1.00",
            f"[bold magenta]{breakdown['importance']:.4f}[/bold magenta]",
        )
        console.print(table)

        # Frequency breakdown
        console.print(f"Frequency: Asked in [bold]{freq['freq_hits_F']}[/bold] of last [bold]{freq['freq_window']}[/bold] exams.")
        if freq["hit_attempts"]:
            console.print(f"Hit Attempts: {', '.join(freq['hit_attempts'])}")
        console.print(f"Window Attempts: {', '.join(freq['window_attempts'])}")

        # Contributing appearances
        apps = payload.get("appearances", [])
        if apps:
            app_table = Table(title=f"Contributing Appearances ({len(apps)} items)")
            app_table.add_column("App ID", style="cyan")
            app_table.add_column("Attempt")
            app_table.add_column("Signal")
            app_table.add_column("Label")
            app_table.add_column("Marks", justify="right")
            app_table.add_column("Share", justify="right")
            app_table.add_column("m(a,s)", justify="right")
            app_table.add_column("Age (m)", justify="right")
            app_table.add_column("Decay", justify="right")
            app_table.add_column("Contribution", style="bold green", justify="right")

            for a in apps:
                app_table.add_row(
                    str(a["appearance_id"]),
                    a["attempt_id"],
                    a["signal_class"],
                    a["display_label"],
                    str(a["marks"] or 0),
                    f"{a['share']:.2f}",
                    f"{a['attributed_marks_m']:.2f}",
                    str(a["age_months"]),
                    f"{a['decay']:.4f}",
                    f"{a['contribution']:.4f}",
                )
            console.print(app_table)
        else:
            console.print("[dim]No historical exam/practice appearances recorded for this subtopic.[/dim]")


@app.command("coverage")
def cmd_coverage() -> None:
    """Display ingestion coverage and weighted syllabus coverage."""
    session_factory = get_session_factory()
    with session_factory() as session:
        cov = compute_weighted_coverage(session, user_id=1)
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
