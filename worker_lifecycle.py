"""Identify the application-owned worker before signalling its recorded PID."""
import json
import os
import signal
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
STATE_PATH = PROJECT_ROOT / "data" / "runtime" / "intel-worker.json"


def record_worker(pid: int, token: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"pid": pid, "token": token}))


def clear_worker(token: str) -> None:
    if STATE_PATH.exists() and json.loads(STATE_PATH.read_text())["token"] == token:
        STATE_PATH.unlink()


def stop_recorded_worker() -> bool:
    if not STATE_PATH.exists():
        return False
    state = json.loads(STATE_PATH.read_text())
    pid, token = int(state["pid"]), state["token"]
    if os.name == "nt":
        result = subprocess.run(["powershell", "-NoProfile", "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"],
            capture_output=True, text=True, check=False)
    else:
        # GNU ps can truncate a long uv/Python path before the ownership token.
        result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "command="],
                                capture_output=True, text=True, check=False)
    command = result.stdout
    if result.returncode != 0 or not command.strip():
        clear_worker(token)
        return False
    if "caf intel worker" not in command or token not in command:
        raise RuntimeError("Recorded worker PID no longer matches its application ownership token")
    os.kill(pid, signal.SIGTERM)
    clear_worker(token)
    return True
