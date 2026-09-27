#!/usr/bin/env python3
"""Launch CA Final Study Companion services and auto-open the web interface.

Run this every time you want to use the application:
    python start.py
"""

import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
BASE_URL = "http://localhost:8000"
HEALTH_URL = f"{BASE_URL}/api/v1/health"


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


def ensure_db_running() -> tuple[str | None, bool]:
    """Ensure database is accessible. Returns (docker_bin, used_docker)."""
    host, port = parse_db_host_port()

    # 1. Already reachable
    if is_db_reachable(host, port) or (port != 5432 and is_db_reachable(host, 5432)):
        print(f"✓ PostgreSQL database is active and reachable.")
        return None, False

    # 2. Need Docker
    docker_bin = shutil.which("docker")
    if not docker_bin:
        print(f"❌ Error: Database is not running, and Docker is not installed.")
        print("   Please start your PostgreSQL service or Docker Desktop.")
        sys.exit(1)

    res = subprocess.run([docker_bin, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        print("❌ Error: Docker daemon is not running.")
        print("   Please start Docker Desktop and re-run python start.py.")
        sys.exit(1)

    print("🐘 Starting PostgreSQL database container...")
    subprocess.run([docker_bin, "compose", "up", "-d"], cwd=PROJECT_ROOT, check=True)
    return docker_bin, True


def find_uv() -> str:
    """Find uv binary."""
    uv_bin = shutil.which("uv")
    if not uv_bin:
        if platform.system() == "Windows":
            candidate = Path(sys.prefix) / "Scripts" / "uv.exe"
        else:
            candidate = Path(sys.prefix) / "bin" / "uv"
        if candidate.exists():
            uv_bin = str(candidate)

    if not uv_bin:
        print("❌ Error: 'uv' package manager not found. Please run 'python setup.py' first.")
        sys.exit(1)
    return uv_bin


def wait_for_server(timeout_seconds: int = 30) -> bool:
    """Poll health endpoint until server responds."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.Request(HEALTH_URL)
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionResetError, OSError):
            time.sleep(0.5)
    return False


def main() -> None:
    print("=" * 60)
    print("  Starting CA Final Study Companion...")
    print("=" * 60)

    docker_bin, used_docker = ensure_db_running()
    uv_bin = find_uv()

    # Launch FastAPI backend + SPA server
    print("🚀 Launching application server on port 8000...")
    serve_cmd = [uv_bin, "run", "caf", "serve", "--host", "0.0.0.0", "--port", "8000"]

    server_proc = subprocess.Popen(
        serve_cmd,
        cwd=PROJECT_ROOT,
    )

    try:
        # Wait for HTTP readiness
        print("⏳ Waiting for web service to respond...", end="", flush=True)
        ready = wait_for_server(30)
        if ready:
            print(" ready!\n")
            print("╔══════════════════════════════════════════════════════════════╗")
            print("║             CA Final Study Companion is Live!                ║")
            print("║                                                              ║")
            print("║  📖 Study App:     http://localhost:8000                     ║")
            print("║  🛠️  Curator Tool:  http://localhost:8000/curator             ║")
            print("║  📚 API Reference: http://localhost:8000/docs                ║")
            print("║                                                              ║")
            print("║  Press Ctrl+C at any time to safely shut down.               ║")
            print("╚══════════════════════════════════════════════════════════════╝\n")

            # Open in browser automatically
            try:
                webbrowser.open(BASE_URL)
            except Exception:
                pass
        else:
            print("\n⚠️ Server started but health check timed out. You can try opening http://localhost:8000 manually.")

        # Keep running until Ctrl+C
        server_proc.wait()

    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down CA Final Study Companion...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

        if used_docker and docker_bin:
            print("💾 Stopping database container (data safely stored)...")
            subprocess.run([docker_bin, "compose", "stop"], cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("✓ All services stopped cleanly. See you next study session!\n")


if __name__ == "__main__":
    main()
