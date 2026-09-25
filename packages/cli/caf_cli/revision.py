"""CLI commands for spaced-repetition revision queue."""

from rich.console import Console
from rich.table import Table
import typer

from caf_db.engine import get_session_factory
from caf_l5 import get_revision_due_list, record_revision_outcome

app = typer.Typer(help="Spaced-repetition revision commands")
console = Console()


@app.command("list")
def cmd_list_due(
    paper: str | None = typer.Option(None, "--paper", "-p", help="Filter by paper code (e.g. P1)"),
) -> None:
    """List subtopics due for spaced-repetition revision."""
    session_factory = get_session_factory()
    with session_factory() as session:
        due = get_revision_due_list(session=session, user_id=1, paper_id=paper)

        console.print(f"\n[bold cyan]Spaced Repetition Revision Queue[/bold cyan]")
        console.print(f"Total Due Today: [bold green]{len(due)}[/bold green]")

        if not due:
            console.print("[dim]No subtopics are currently due for revision. Great job![/dim]")
            return

        table = Table(title="Due for Revision")
        table.add_column("Node ID", style="cyan")
        table.add_column("Paper", style="bold magenta")
        table.add_column("Subtopic Name", style="bold")
        table.add_column("Importance", justify="right", style="magenta")
        table.add_column("Due Date", justify="center")
        table.add_column("Overdue", justify="right", style="bold red")
        table.add_column("Stage (k)", justify="center")
        table.add_column("Interval", justify="right")

        for item in due:
            table.add_row(
                item["node_id"],
                item["paper_code"],
                item["node_name"][:38],
                f"{item['importance']:.4f}",
                item["due_date"],
                f"{item['overdue_days']}d",
                str(item["revision_count_k"]),
                f"{item['interval_days']}d",
            )

        console.print(table)


@app.command("log")
def cmd_log_revision(
    node_id: str = typer.Argument(..., help="Subtopic Node ID (e.g. P1-GDH25Q)"),
    outcome: str = typer.Option(
        "ok", "--outcome", "-o", help="Revision outcome: 'ok' (passed) or 'shaky' (needs review)"
    ),
) -> None:
    """Log a completed revision for a subtopic ('ok' or 'shaky')."""
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            res = record_revision_outcome(
                session=session,
                node_id=node_id,
                outcome=outcome,
                user_id=1,
            )
            style = "green" if outcome == "ok" else "yellow"
            console.print(
                f"[{style}]✓ Revision logged successfully![/{style}] "
                f"Node: [bold]{res['node_id']}[/bold], "
                f"Outcome: [bold]{res['outcome']}[/bold], "
                f"Recorded At: {res['at']}"
            )
        except ValueError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)
