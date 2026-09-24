"""Main entrypoint for the caf CLI."""

import subprocess
import sys
from pathlib import Path
from alembic import command
from alembic.config import Config
from rich.console import Console
from rich.table import Table
import sqlalchemy as sa
import typer

from caf_common.logging import setup_logging
from caf_common.settings import get_settings
from caf_db.engine import get_engine, get_session_factory
from caf_db.grants import apply_grants

app = typer.Typer(
    name="caf",
    help="CA Final Study Companion — Operating System & Exam Intelligence CLI",
    add_completion=False,
)
db_app = typer.Typer(help="Database management commands")
taxonomy_app = typer.Typer(help="L0 Reference & Taxonomy commands")
acquire_app = typer.Typer(help="L1 Acquisition commands")
extract_app = typer.Typer(help="L2 Extraction commands")
classify_app = typer.Typer(help="L3 Classification commands")
curate_app = typer.Typer(help="L4 Curation commands")
intel_app = typer.Typer(help="L5 Intelligence commands")

app.add_typer(db_app, name="db")
app.add_typer(taxonomy_app, name="taxonomy")
app.add_typer(acquire_app, name="acquire")
app.add_typer(extract_app, name="extract")
app.add_typer(classify_app, name="classify")
app.add_typer(curate_app, name="curate")
app.add_typer(intel_app, name="intel")

console = Console()


@app.callback()
def main_callback() -> None:
    setup_logging()


def _get_alembic_config() -> Config:
    ini_path = Path("alembic.ini")
    if not ini_path.exists():
        ini_path = Path("packages/db/alembic.ini")
    cfg = Config(str(ini_path))
    settings = get_settings()
    url = settings.DATABASE_URL or settings.database.url
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


# ==============================================================================
# System Status Command
# ==============================================================================
@app.command("status")
def status() -> None:
    """Display overall system status, DB health, target attempt, and pipeline stats."""
    settings = get_settings()
    console.print(f"[bold cyan]CA Final Study Companion[/bold cyan] (env: {settings.app.env})")
    console.print(f"Target Attempt: [bold green]{settings.app.target_attempt_id}[/bold green]")

    # Check DB Connection
    db_ok = False
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1;"))
            db_ok = True
    except Exception as exc:
        console.print(f"[bold red]Database: UNREACHABLE[/bold red] ({exc})")

    if db_ok:
        console.print("[bold green]Database: CONNECTED[/bold green]")
        session_factory = get_session_factory()
        with session_factory() as session:
            # Query recent runs
            try:
                runs = session.execute(
                    sa.text(
                        "SELECT id, stage, status, started_at, finished_at, error "
                        "FROM ops.run ORDER BY id DESC LIMIT 5"
                    )
                ).fetchall()

                table = Table(title="Recent Pipeline Runs (ops.run)")
                table.add_column("Run ID", style="cyan")
                table.add_column("Stage", style="magenta")
                table.add_column("Status", style="bold")
                table.add_column("Started At")
                table.add_column("Finished At")
                table.add_column("Error", style="red")

                for r in runs:
                    status_style = "green" if r.status == "ok" else ("yellow" if r.status == "running" else "red")
                    table.add_row(
                        str(r.id),
                        r.stage,
                        f"[{status_style}]{r.status}[/{status_style}]",
                        str(r.started_at),
                        str(r.finished_at or "-"),
                        str(r.error or "-"),
                    )
                console.print(table)
            except Exception:
                console.print("[yellow]ops.run table not initialized yet. Run 'caf db migrate'.[/yellow]")


# ==============================================================================
# Database Commands
# ==============================================================================
@db_app.command("up")
def db_up() -> None:
    """Start the PostgreSQL container via docker compose."""
    try:
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        console.print("[green]PostgreSQL container started.[/green]")
    except FileNotFoundError:
        console.print("[yellow]Docker command not found. Ensure Docker Desktop is installed or run local Postgres.[/yellow]")
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Failed to start container: {exc}[/red]")


@db_app.command("ping")
def db_ping() -> None:
    """Test connection to the database."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1;"))
            console.print("[green]Database connection successful![/green]")
    except Exception as exc:
        console.print(f"[red]Database connection failed: {exc}[/red]")
        sys.exit(1)


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply all pending Alembic migrations (upgrade head)."""
    cfg = _get_alembic_config()
    command.upgrade(cfg, "head")
    console.print("[green]Migrations successfully applied to head.[/green]")


@db_app.command("rollback")
def db_rollback(steps: int = 1) -> None:
    """Roll back Alembic migrations by N steps."""
    cfg = _get_alembic_config()
    command.downgrade(cfg, f"-{steps}")
    console.print(f"[green]Successfully rolled back {steps} migration(s).[/green]")


@db_app.command("grants")
def db_grants() -> None:
    """Apply database schema and role permissions idempotently."""
    apply_grants()
    console.print("[green]Database roles and schema grants applied successfully.[/green]")


# ==============================================================================
# L0 Taxonomy Stubs
# ==============================================================================
@taxonomy_app.command("load")
def taxonomy_load(apply: bool = typer.Option(False, "--apply", help="Apply changes to database")) -> None:
    """Validate and optionally load taxonomy YAML into ref schema."""
    from caf_l0.loader import TaxonomyLoader
    from caf_common.run_context import open_run

    loader = TaxonomyLoader()
    plan = loader.plan()
    loader.print_plan(plan)

    if not apply:
        console.print("\n[yellow]Dry-run validation mode. Pass --apply to persist changes.[/yellow]")
        return

    with open_run("l0.load", {"apply": True}) as run:
        session_factory = get_session_factory()
        with session_factory() as session:
            version_id = loader.apply(session, plan)
            run.stats = {"taxonomy_version_id": version_id, "entities": {k: len(v) for k, v in plan.items() if isinstance(v, list)}}
            console.print(f"[bold green]Successfully loaded taxonomy version {version_id} into ref schema.[/bold green]")


# ==============================================================================
# L1 Acquisition Commands
# ==============================================================================
@acquire_app.command("discover")
def acquire_discover(
    source_id: str | None = typer.Option(None, "--source", help="Specific source ID to discover"),
) -> None:
    """Discover official PDF links from configured seed sources."""
    import tomllib
    from caf_common.run_context import open_run
    from caf_l1.discover import LinkDiscoverer
    from caf_l1.robots import PolitenessManager

    settings = get_settings()
    sources_file = Path("config/sources.toml")
    if not sources_file.exists():
        console.print("[red]config/sources.toml not found[/red]")
        return

    with open(sources_file, "rb") as f:
        cfg = tomllib.load(f)

    defaults = cfg.get("defaults", {})
    sources = cfg.get("source", [])
    if source_id:
        sources = [s for s in sources if s.get("id") == source_id]

    politeness = PolitenessManager(
        user_agent=defaults.get("user_agent", "CAFinalStudyCompanion/0.1"),
        min_delay_s=defaults.get("min_delay_s", 5.0),
        max_delay_s=defaults.get("max_delay_s", 10.0),
    )

    discoverer = LinkDiscoverer(sources=sources, politeness=politeness)

    with open_run("l1.discover", {"sources": [s["id"] for s in sources]}) as run:
        session_factory = get_session_factory()
        total_discovered = 0
        with session_factory() as session:
            for s in sources:
                count = discoverer.discover_source(s, session, run_id=run.id)
                total_discovered += count
            run.stats = {"total_discovered": total_discovered}
        console.print(f"[bold green]Discovery complete. Discovered {total_discovered} link(s).[/bold green]")


@acquire_app.command("fetch")
def acquire_fetch(
    limit: int = typer.Option(20, "--limit", help="Maximum documents to download"),
) -> None:
    """Fetch pending candidate PDFs using polite rate-limits and store in blob store."""
    import tomllib
    from caf_common.blob_store import BlobStore
    from caf_common.run_context import open_run
    from caf_l1.fetcher import DocumentFetcher
    from caf_l1.robots import PolitenessManager

    settings = get_settings()
    sources_file = Path("config/sources.toml")
    with open(sources_file, "rb") as f:
        cfg = tomllib.load(f)
    defaults = cfg.get("defaults", {})

    politeness = PolitenessManager(
        user_agent=defaults.get("user_agent", "CAFinalStudyCompanion/0.1"),
        min_delay_s=defaults.get("min_delay_s", 5.0),
        max_delay_s=defaults.get("max_delay_s", 10.0),
    )
    blob_store = BlobStore(settings.storage.blob_dir)
    fetcher = DocumentFetcher(blob_store=blob_store, politeness=politeness)

    with open_run("l1.fetch", {"limit": limit}) as run:
        session_factory = get_session_factory()
        with session_factory() as session:
            downloaded = fetcher.fetch_pending(session, limit=limit, run_id=run.id)
            run.stats = {"downloaded": downloaded}
        console.print(f"[bold green]Fetch run complete. Downloaded {downloaded} document(s).[/bold green]")


@acquire_app.command("import")
def acquire_import(
    path: Path = typer.Argument(..., help="Path to PDF file or directory to import"),
) -> None:
    """Manually import PDF(s) into blob store and ingest.document table."""
    from caf_common.blob_store import BlobStore
    from caf_common.run_context import open_run
    from caf_l1.importer import ManualImporter

    settings = get_settings()
    blob_store = BlobStore(settings.storage.blob_dir)
    importer = ManualImporter(blob_store=blob_store)

    with open_run("l1.import", {"path": str(path)}) as run:
        session_factory = get_session_factory()
        with session_factory() as session:
            if path.is_dir():
                imported = importer.import_directory(path, session, run_id=run.id)
                count = len(imported)
            else:
                doc = importer.import_file(path, session, run_id=run.id)
                count = 1 if doc else 0
            run.stats = {"imported_count": count}
        console.print(f"[bold green]Successfully imported {count} document(s).[/bold green]")


@acquire_app.command("catalog")
def acquire_catalog(
    status: str = typer.Option("inferred", "--status", help="Filter by catalog_status"),
) -> None:
    """List documents in the catalogue pending confirmation."""
    from caf_db.models.ingest import Document

    session_factory = get_session_factory()
    with session_factory() as session:
        docs = session.execute(
            sa.select(Document).where(Document.catalog_status == status).order_by(Document.id.desc())
        ).scalars().all()

        table = Table(title=f"Documents with status '{status}'")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Attempt", style="green")
        table.add_column("Paper", style="magenta")
        table.add_column("Doc Type", style="yellow")
        table.add_column("Status", style="bold")
        table.add_column("Pages")

        for d in docs:
            table.add_row(
                str(d.id),
                (d.title or "-")[:45],
                d.attempt_id or "-",
                d.paper_id or "-",
                d.doc_type_id or "-",
                d.catalog_status,
                str(d.page_count or "-"),
            )
        console.print(table)


@acquire_app.command("confirm")
def acquire_confirm(doc_id: int = typer.Argument(..., help="Document ID to confirm")) -> None:
    """Confirm metadata for a catalogued document."""
    from caf_l1.catalog import confirm_document

    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            doc = confirm_document(session, doc_id)
            console.print(f"[bold green]Document {doc.id} ({doc.title}) successfully confirmed.[/bold green]")
        except Exception as exc:
            console.print(f"[bold red]Confirmation failed: {exc}[/bold red]")


# ==============================================================================
# L6 Serve Command
# ==============================================================================
@app.command("serve")
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Start the FastAPI backend server."""
    import uvicorn
    uvicorn.run("caf_api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
