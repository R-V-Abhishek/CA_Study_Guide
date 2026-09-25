"""CLI commands for next-week study planning."""

from rich.console import Console
from rich.table import Table
import typer

from caf_db.engine import get_session_factory
from caf_l5 import generate_study_plan

app = typer.Typer(help="Study planning commands")
console = Console()


@app.callback(invoke_without_command=True)
def cmd_plan(
    ctx: typer.Context,
    paper: str | None = typer.Option(None, "--paper", "-p", help="Filter by paper code (e.g. P1)"),
    group: int | None = typer.Option(None, "--group", "-g", help="Filter by group (1 or 2)"),
    hours: float | None = typer.Option(None, "--hours", "-h", help="Override study hours per week"),
) -> None:
    """Generate and display next-week study plan with factual priority justifications."""
    session_factory = get_session_factory()
    with session_factory() as session:
        plan = generate_study_plan(
            session=session,
            user_id=1,
            paper_id=paper,
            group_no=group,
            hours_per_week=hours,
        )

        items = plan["items"]
        console.print(f"\n[bold cyan]Next-Week Study Plan[/bold cyan]")
        console.print(
            f"Budget: [bold]{plan['budget_items']}[/bold] subtopics "
            f"({plan['hours_per_week']} hrs/week @ {plan['minutes_per_subtopic']} min/subtopic) | "
            f"Allocated: [bold green]{plan['total_allocated']}[/bold green]"
        )

        if not items:
            console.print("[dim]No candidate subtopics available for planning.[/dim]")
            return

        table = Table(title="Allocated Subtopics for Study")
        table.add_column("#", justify="right", style="cyan")
        table.add_column("Paper", style="bold magenta")
        table.add_column("Subtopic Name", style="bold")
        table.add_column("Chapter", style="dim")
        table.add_column("Score", justify="right", style="bold green")
        table.add_column("Status", justify="center")
        table.add_column("Weak?", justify="center")
        table.add_column("Justification (Reason)", style="italic")

        for idx, item in enumerate(items, 1):
            weak_str = "[bold red]YES[/bold red]" if item["weak"] else "-"
            status_style = (
                "[yellow]in_progress[/yellow]"
                if item["status"] == "in_progress"
                else "not_started"
            )
            table.add_row(
                str(idx),
                item["paper_code"],
                item["node_name"][:35],
                item["chapter_name"][:25],
                f"{item['priority_score']:.4f}",
                status_style,
                weak_str,
                item["reason"],
            )

        console.print(table)
