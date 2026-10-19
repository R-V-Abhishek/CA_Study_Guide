"""Exercise command-width handling without a database or a real queue worker."""

from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import worker_lifecycle


def test_owned_process_after_long_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_lifecycle, "STATE_PATH", tmp_path / "worker.json")
    monkeypatch.setenv("COLUMNS", "80")
    token = secrets.token_hex(12)
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)",
                               "padding" * 100, "caf", "intel", "worker", "--owner-token", token])
    try:
        worker_lifecycle.record_worker(process.pid, token)
        assert worker_lifecycle.stop_recorded_worker()
        process.wait(timeout=5)
        assert not worker_lifecycle.STATE_PATH.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
