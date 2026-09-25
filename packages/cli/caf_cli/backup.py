"""CLI commands for backup creation, verification, and rotation."""

from pathlib import Path
from rich.console import Console
from rich.table import Table
import typer

from caf_common.backup import create_backup, list_backups, verify_backup
from caf_db.engine import get_session_factory

app = typer.Typer(help="Backup and disaster recovery commands")
console = Console()


@app.command("run")
def cmd_run(
    backup_dir: Path | None = typer.Option(
        None, "--backup-dir", "-d", help="Directory where backup dumps are stored"
    ),
    target_dir: Path | None = typer.Option(
        None, "--target-dir", "-t", help="Secondary sync target (e.g. external volume / cloud sync folder)"
    ),
) -> None:
    """Create a full database dump, sync blobs and configs, and enforce retention."""
    session_factory = get_session_factory()
    with session_factory() as session:
        console.print("[bold cyan]Starting full system backup...[/bold cyan]")
        try:
            manifest = create_backup(
                session=session,
                backup_dir=backup_dir,
                target_dir=target_dir,
            )
            table = Table(title="Backup Succeeded", show_header=True)
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="magenta")

            table.add_row("Dump File", manifest.dump_file.name)
            table.add_row("Dump Path", str(manifest.dump_file))
            table.add_row("Size", f"{manifest.dump_size_bytes / (1024 * 1024):.2f} MB ({manifest.dump_size_bytes} bytes)")
            table.add_row("Blobs Synced", str(manifest.blobs_copied))
            table.add_row("Configs Archived", str(manifest.configs_copied))
            table.add_row("Created At", manifest.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
            table.add_row("Retention Policy", "14 daily + 8 weekly preserved")

            console.print(table)
            console.print("[bold green]✓ Nightly backup manifest recorded in ops.event (code=BACKUP_OK).[/bold green]")
        except Exception as exc:
            console.print(f"[bold red]Backup failed:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command("verify")
def cmd_verify(
    dump_file: Path | None = typer.Option(
        None, "--dump-file", "-f", help="Specific dump file to verify (default: latest)"
    ),
    scratch_db: str = typer.Option(
        "caf_verify", "--scratch-db", help="Name of temporary scratch database"
    ),
) -> None:
    """Monthly restore drill: restore dump into scratch DB and verify row counts across critical tables."""
    session_factory = get_session_factory()
    with session_factory() as session:
        console.print("[bold cyan]Running monthly backup verification drill...[/bold cyan]")
        try:
            res = verify_backup(
                session=session,
                dump_file=dump_file,
                scratch_db_name=scratch_db,
            )

            status_color = "bold green" if res.verified else "bold red"
            table = Table(title=f"Backup Verification Report: {res.dump_file.name}", show_header=True)
            table.add_column("Table", style="cyan")
            table.add_column("Live Count", justify="right")
            table.add_column("Restored Count", justify="right")
            table.add_column("Status", justify="center")

            for t_name in sorted(res.live_counts.keys()):
                live_cnt = res.live_counts.get(t_name, 0)
                rest_cnt = res.restored_counts.get(t_name, 0)
                match = (live_cnt == rest_cnt)
                table.add_row(
                    t_name,
                    str(live_cnt),
                    str(rest_cnt),
                    "[green]MATCH[/green]" if match else "[red]MISMATCH[/red]",
                )

            console.print(table)
            console.print(f"\nVerification Result: [{status_color}]{'PASSED' if res.verified else 'FAILED'}[/{status_color}]")
            console.print(f"[dim]{res.message}[/dim]")

            if not res.verified:
                raise typer.Exit(code=1)

        except Exception as exc:
            console.print(f"[bold red]Verification drill failed:[/bold red] {exc}")
            raise typer.Exit(code=1)


@app.command("list")
def cmd_list(
    backup_dir: Path | None = typer.Option(
        None, "--backup-dir", "-d", help="Directory where backup dumps are stored"
    ),
) -> None:
    """List all available backup dumps with sizes and age."""
    backups = list_backups(backup_dir)
    if not backups:
        console.print("[dim]No database backups found.[/dim]")
        return

    table = Table(title="Database Backups (data/backups)", show_header=True)
    table.add_column("Filename", style="cyan")
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Age", justify="right")
    table.add_column("Created At", style="dim")

    for b in backups:
        age_str = f"{b['age_hours']:.1f} hrs ago" if b['age_hours'] < 48 else f"{b['age_hours'] / 24:.1f} days ago"
        age_style = "green" if b['age_hours'] <= 48 else "yellow"
        table.add_row(
            b["name"],
            f"{b['size_mb']} MB",
            f"[{age_style}]{age_str}[/{age_style}]",
            b["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    console.print(table)
