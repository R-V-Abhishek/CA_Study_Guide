#!/usr/bin/env python3
"""One-time bootstrap setup script for CA Final Study Companion.

Works across macOS, Windows, and Linux using Python standard library only.
Run this once from the project root:
    python setup.py
"""

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Minimum required Python version
MIN_PYTHON = (3, 12)
PROJECT_ROOT = Path(__file__).parent.resolve()


def print_step(step_num: int, total_steps: int, title: str) -> None:
    """Print a clean step header."""
    print(f"\n[{step_num}/{total_steps}] {title}")
    print("─" * 60)


def check_python_version() -> None:
    """Ensure Python >= 3.12."""
    if sys.version_info < MIN_PYTHON:
        print(f"❌ Error: Python 3.12 or newer is required.")
        print(f"   Currently running: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        print("   Please install Python 3.12+ from https://www.python.org/downloads/ and try again.")
        sys.exit(1)
    print(f"✓ Python version: {platform.python_version()} (OK)")


def parse_db_host_port() -> tuple[str, int]:
    """Read DB host and port from .env or defaults."""
    env_path = PROJECT_ROOT / ".env"
    host = "127.0.0.1"
    port = 5433
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("PG_HOST="):
                host = line.split("=", 1)[1].strip()
            elif line.startswith("PG_PORT="):
                try:
                    port = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return host, port


def is_db_reachable(host: str, port: int) -> bool:
    """Test TCP socket connection to database."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def ensure_database() -> None:
    """Ensure PostgreSQL is accessible, starting Docker if needed."""
    host, port = parse_db_host_port()

    # 1. Check if database is already running and reachable
    if is_db_reachable(host, port):
        print(f"✓ PostgreSQL database is already running on {host}:{port} (OK)")
        return

    # Check common default port 5432 as well if port was 5433
    if port != 5432 and is_db_reachable(host, 5432):
        print(f"✓ PostgreSQL is detected running on {host}:5432 (OK)")
        return

    # 2. Database not reachable; check Docker
    docker_bin = shutil.which("docker")
    if not docker_bin:
        print(f"❌ Error: Database is not running on {host}:{port}, and Docker is not installed.")
        if platform.system() == "Darwin":
            print("   Please install Docker Desktop for Mac: https://www.docker.com/products/docker-desktop/")
        elif platform.system() == "Windows":
            print("   Please install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/")
        else:
            print("   Please install Docker: https://docs.docker.com/engine/install/")
        sys.exit(1)

    # Check if Docker daemon is running
    res = subprocess.run([docker_bin, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        print("❌ Error: Docker daemon is not running.")
        print("   Please start Docker Desktop and re-run setup.")
        sys.exit(1)

    print("✓ Docker engine detected (OK)")
    print("Starting PostgreSQL container via docker compose...")
    subprocess.run([docker_bin, "compose", "up", "-d"], cwd=PROJECT_ROOT, check=True)

    print("Waiting for PostgreSQL database to be ready...", end="", flush=True)
    for _ in range(30):
        if is_db_reachable(host, port):
            print(" ready!")
            return
        time.sleep(2)
        print(".", end="", flush=True)

    print("\n⚠️ Database start timed out. Continuing with setup...")


def setup_env_file() -> None:
    """Create .env file from .env.example if missing and prompt for API key."""
    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"

    if env_path.exists():
        print("✓ .env file already exists (skipping creation)")
        return

    if not example_path.exists():
        print("⚠️ Warning: .env.example not found. Creating basic .env...")
        env_content = (
            "PG_SUPERUSER=postgres\n"
            "PG_SUPERUSER_PASSWORD=postgres_dev_password\n"
            "PG_HOST=127.0.0.1\n"
            "PG_PORT=5433\n"
            "PG_DATABASE=caf\n"
            "DATABASE_URL=postgresql+psycopg://postgres:postgres_dev_password@127.0.0.1:5433/caf\n"
            "GEMINI_API_KEY=\n"
            "CAF_ENV=development\n"
            "CAF_DATA_DIR=./data\n"
        )
        env_path.write_text(env_content, encoding="utf-8")
    else:
        shutil.copy(example_path, env_path)

    print("✓ Created .env from .env.example")

    # Interactive prompt for GEMINI_API_KEY
    print("\n   [Google Gemini API Key]")
    print("   The L3 AI Classification pipeline requires a Google Gemini API Key.")
    print("   (If you do not have one right now, press Enter to skip and add it later in .env)")
    try:
        api_key = input("   Enter your GEMINI_API_KEY (or press Enter): ").strip()
    except (EOFError, KeyboardInterrupt):
        api_key = ""

    if api_key:
        content = env_path.read_text(encoding="utf-8")
        if "GEMINI_API_KEY=" in content:
            new_lines = []
            for line in content.splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    new_lines.append(f"GEMINI_API_KEY={api_key}")
                else:
                    new_lines.append(line)
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            with env_path.open("a", encoding="utf-8") as f:
                f.write(f"\nGEMINI_API_KEY={api_key}\n")
        print("✓ Saved GEMINI_API_KEY to .env")
    else:
        print("ℹ️ No API key entered. You can add GEMINI_API_KEY to your .env file at any time.")


def ensure_uv() -> str:
    """Check for uv package manager; auto-install if missing."""
    uv_bin = shutil.which("uv")
    if uv_bin:
        print(f"✓ Found uv: {uv_bin}")
        return uv_bin

    print("ℹ️ 'uv' package manager not found in PATH. Installing uv via pip...")
    res = subprocess.run([sys.executable, "-m", "pip", "install", "uv"], check=False)
    uv_bin = shutil.which("uv")
    if not uv_bin:
        # Check standard user local bins or python Scripts folder
        if platform.system() == "Windows":
            candidate = Path(sys.prefix) / "Scripts" / "uv.exe"
        else:
            candidate = Path(sys.prefix) / "bin" / "uv"
        if candidate.exists():
            uv_bin = str(candidate)

    if not uv_bin:
        print("❌ Error: Could not install 'uv'. Please install it manually:")
        print("   pip install uv")
        sys.exit(1)

    print(f"✓ Installed uv: {uv_bin}")
    return uv_bin


def run_command(cmd: list[str], desc: str) -> None:
    """Run a subprocess command and handle errors clearly."""
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print(f"\n❌ Error during step: {desc}")
        print(f"   Command failed with exit code {res.returncode}: {' '.join(cmd)}")
        sys.exit(res.returncode)


def main() -> None:
    """Execute all setup steps sequentially."""
    print("\n" + "=" * 60)
    print("  CA Final Study Companion — One-Time Setup")
    print("=" * 60)

    total_steps = 7

    # Step 1: Python Version
    print_step(1, total_steps, "Checking Python version")
    check_python_version()

    # Step 2: Environment File
    print_step(2, total_steps, "Configuring environment (.env)")
    setup_env_file()

    # Step 3: Database Verification / Start
    print_step(3, total_steps, "Connecting to PostgreSQL database")
    ensure_database()

    # Step 4: Install Dependencies
    print_step(4, total_steps, "Installing Python dependencies with uv")
    uv_bin = ensure_uv()
    run_command([uv_bin, "sync"], "Python dependencies installation")

    # Step 5: Database Migrations
    print_step(5, total_steps, "Applying database migrations (Alembic)")
    run_command([uv_bin, "run", "alembic", "upgrade", "head"], "Database schema migrations")

    # Step 6: Database Grants
    print_step(6, total_steps, "Applying role and schema permissions")
    run_command([uv_bin, "run", "caf", "db", "grants"], "Database role permissions")

    # Step 7: Load Syllabus Taxonomy
    print_step(7, total_steps, "Loading canonical syllabus taxonomy into database")
    run_command([uv_bin, "run", "caf", "taxonomy", "load", "--apply"], "Taxonomy syllabus loading")

    # Verification banner
    print("\n" + "=" * 60)
    print("  🎉 Setup Complete! Everything is ready.")
    print("=" * 60)
    print("\nTo start your study companion now:")
    if platform.system() == "Windows":
        print("  ▶ Run: python start.py   (or double-click start.bat)")
    else:
        print("  ▶ Run: python3 start.py  (or ./start.sh)")

    print("\nYour applications will be available at:")
    print("  📖 Student Study App: http://localhost:8000")
    print("  🛠️ Curator Tool:     http://localhost:8000/curator")
    print("  📚 API Docs:          http://localhost:8000/docs\n")


if __name__ == "__main__":
    main()
