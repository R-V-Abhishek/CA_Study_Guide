"""CLI commands for mock test logging and tracking."""

from datetime import date, datetime
from rich.console import Console
from rich.table import Table
import sqlalchemy as sa
import typer

from caf_db.engine import get_session_factory
from caf_db.models.app import MockTest
from caf_db.models.ref import Paper

app = typer.Typer(help="Mock test tracker commands")
console = Console()


@app.command("list")
def cmd_list_mock_tests(
    paper: str | None = typer.Option(None, "--paper", "-p", help="Filter by paper code (e.g. P1)"),
) -> None:
    """List mock test results."""
    session_factory = get_session_factory()
    with session_factory() as session:
        query = (
            sa.select(MockTest, Paper.code)
            .join(Paper, Paper.id == MockTest.paper_id)
            .where(MockTest.user_id == 1)
        )
        if paper:
            query = query.where((Paper.code == paper.upper()) | (Paper.id == paper))
        query = query.order_by(MockTest.taken_on.desc())

        rows = session.execute(query).all()

        console.print(f"\n[bold cyan]Mock Test Performance Log[/bold cyan]")
        if not rows:
            console.print("[dim]No mock tests recorded yet. Log your first mock test with 'caf mock-test log'![/dim]")
            return

        table = Table(title="Mock Test Attempts")
        table.add_column("ID", style="cyan")
        table.add_column("Paper", style="bold magenta")
        table.add_column("Label", style="bold")
        table.add_column("Score", justify="right")
        table.add_column("Max", justify="right")
        table.add_column("Percentage", justify="right", style="bold green")
        table.add_column("Date", justify="center")
        table.add_column("Notes", style="dim")

        for mt, p_code in rows:
            pct = (float(mt.score) / float(mt.max_score) * 100.0) if float(mt.max_score) > 0 else 0.0
            table.add_row(
                str(mt.id),
                p_code,
                mt.label or "-",
                f"{mt.score:.1f}",
                f"{mt.max_score:.1f}",
                f"{pct:.1f}%",
                mt.taken_on.isoformat(),
                mt.notes or "-",
            )

        console.print(table)


@app.command("log")
def cmd_log_mock_test(
    paper: str = typer.Option(..., "--paper", "-p", help="Paper code (e.g. P1)"),
    score: float = typer.Option(..., "--score", "-s", help="Score achieved"),
    max_score: float = typer.Option(100.0, "--max-score", "-m", help="Maximum marks (default 100)"),
    taken_on: str | None = typer.Option(
        None, "--date", "-d", help="Date taken in YYYY-MM-DD format (default: today)"
    ),
    label: str | None = typer.Option(None, "--label", "-l", help="Test label (e.g. 'ICAI MTP Series 1')"),
    notes: str | None = typer.Option(None, "--notes", help="Study notes / review areas"),
) -> None:
    """Log a completed mock test attempt."""
    session_factory = get_session_factory()
    with session_factory() as session:
        # Resolve paper
        p_row = session.execute(
            sa.select(Paper).where((Paper.code == paper.upper()) | (Paper.id == paper))
        ).scalar_one_or_none()
        if not p_row:
            console.print(f"[bold red]Paper '{paper}' not found.[/bold red]")
            raise typer.Exit(code=1)

        test_date = date.fromisoformat(taken_on) if taken_on else date.today()

        mt = MockTest(
            user_id=1,
            paper_id=p_row.id,
            label=label,
            score=score,
            max_score=max_score,
            taken_on=test_date,
            notes=notes,
        )
        session.add(mt)
        session.commit()

        pct = (score / max_score * 100.0) if max_score > 0 else 0.0
        console.print(
            f"[bold green]✓ Mock test logged successfully![/bold green] "
            f"ID: [cyan]{mt.id}[/cyan], Paper: [bold]{p_row.code}[/bold], "
            f"Score: [bold]{score}/{max_score}[/bold] ({pct:.1f}%), Date: {test_date}"
        )
