#!/usr/bin/env python3
"""Clean shutdown script for CA Final Study Companion services.

Run:
    python stop.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()


def main() -> None:
    print("Stopping CA Final Study Companion services...")
    docker_bin = shutil.which("docker")
    if docker_bin:
        subprocess.run([docker_bin, "compose", "stop"], cwd=PROJECT_ROOT)
        print("✓ Database container stopped. All your notes and progress are safely preserved.")
    else:
        print("ℹ️ Docker binary not found in PATH.")

    print("✓ Done. To start again, run: python start.py")


if __name__ == "__main__":
    main()
