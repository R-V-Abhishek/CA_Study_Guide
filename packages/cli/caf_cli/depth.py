"""CLI commands for L5 Depth Gate Tooling."""

from rich.console import Console
from rich.table import Table
import typer

from caf_db.engine import get_session_factory
from caf_l5.depth_gate import compute_depth_gate, get_depth_gate_reports

app = typer.Typer(help="L5 Depth Gate tooling commands")
console = Console()


@app.command("gate")
def cmd_gate(
    paper: str = typer.Option(..., "--paper", "-p", help="Paper code or ID (e.g. P1, P2)"),
    band: str = typer.Option(..., "--band", "-b", help="Historical band (e.g. s2017:2019)"),
    top_k: int = typer.Option(50, "--top-k", "-k", help="Top-K subtopics for Jaccard and Spearman (default 50)"),
) -> None:
    """Run Depth Gate computation comparing baseline vs shadow run with the band."""
    session_factory = get_session_factory()
    with session_factory() as session:
        console.print(f"[bold cyan]Running Depth Gate computation for paper [bold]{paper}[/bold], band [bold]{band}[/bold] (top-K={top_k})...[/bold cyan]")
        try:
            report = compute_depth_gate(
                session=session,
                paper=paper,
                band=band,
                top_k=top_k,
                record_report=True,
            )
            
            # Format decision with color
            decision_color = {
                "continue": "bold green",
                "continue_practice_value": "bold yellow",
                "stop": "bold red",
            }.get(report.decision or "", "bold white")
            
            table = Table(title=f"Depth Gate Report: Paper {report.paper_code} | Band {report.band}", show_header=True)
            table.add_column("Metric", style="cyan", no_wrap=True)
            table.add_column("Value", style="magenta")
            
            table.add_row("Paper", report.paper_code)
            table.add_row("Band", report.band)
            table.add_row("Baseline Run ID", str(report.baseline_run_id))
            table.add_row("Shadow Run ID", str(report.shadow_run_id))
            table.add_row("Top K", str(report.top_k))
            table.add_row("Jaccard Similarity", f"{report.jaccard:.4f}" if report.jaccard is not None else "N/A")
            table.add_row("Spearman Rank Correlation", f"{report.spearman:.4f}" if report.spearman is not None else "N/A")
            table.add_row("Newly Asked Nodes", str(report.newly_asked_nodes))
            table.add_row("Units to Review", str(report.units_to_review))
            table.add_row("Est. Review Hours", f"{report.est_review_hours:.1f} hrs" if report.est_review_hours is not None else "0.0 hrs")
            table.add_row("Decision", f"[{decision_color}]{report.decision}[/{decision_color}]")
            table.add_row("Rationale", report.decided_note or "")
            
            console.print(table)
            console.print(f"\n[dim]Recorded Depth Gate Report ID: {report.id}[/dim]")
        except Exception as exc:
            console.print(f"[bold red]Depth gate computation failed:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command("report")
def cmd_report(
    paper: str | None = typer.Option(None, "--paper", "-p", help="Filter by paper code (e.g. P1)"),
    band: str | None = typer.Option(None, "--band", "-b", help="Filter by historical band"),
) -> None:
    """List historical Depth Gate reports."""
    session_factory = get_session_factory()
    with session_factory() as session:
        reports = get_depth_gate_reports(session, paper=paper, band=band)
        if not reports:
            console.print("[dim]No depth gate reports found.[/dim]")
            return

        table = Table(title="Depth Gate Reports History", show_header=True)
        table.add_column("ID", style="dim", justify="right")
        table.add_column("Paper", style="cyan")
        table.add_column("Band", style="magenta")
        table.add_column("Top K", justify="right")
        table.add_column("Jaccard", justify="right")
        table.add_column("Spearman", justify="right")
        table.add_column("New Nodes", justify="right")
        table.add_column("Review Hrs", justify="right")
        table.add_column("Decision", style="bold")
        table.add_column("Created At", style="dim")

        for r in reports:
            decision_color = {
                "continue": "green",
                "continue_practice_value": "yellow",
                "stop": "red",
            }.get(r.decision or "", "white")

            table.add_row(
                str(r.id),
                r.paper_code,
                r.band,
                str(r.top_k),
                f"{r.jaccard:.3f}" if r.jaccard is not None else "-",
                f"{r.spearman:.3f}" if r.spearman is not None else "-",
                str(r.newly_asked_nodes if r.newly_asked_nodes is not None else "-"),
                f"{r.est_review_hours:.1f}" if r.est_review_hours is not None else "-",
                f"[{decision_color}]{r.decision}[/{decision_color}]",
                r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
            )

        console.print(table)
