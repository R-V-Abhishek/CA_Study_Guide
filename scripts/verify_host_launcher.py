"""Exercise the real Linux shell launcher with a newly built application image."""

import json
import os
from pathlib import Path
import subprocess
import sys

import typer

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def verify(image: str = typer.Option(...)) -> None:
    if sys.platform != "linux":
        typer.echo("SKIP: host launcher requires Linux; native Linux CI exercises it")
        return
    root = Path(__file__).resolve().parents[1]
    environment = {key: os.environ[key] for key in ("PATH", "HOME")}
    environment["CAF_HOST_IMAGE"] = image
    environment["CAF_HOST_TEST_CANARY"] = "do-not-export-this-host-environment"
    result = subprocess.run(["sh", str(root / "deploy/caf-host"), "preflight"], env=environment,
                            capture_output=True, text=True, timeout=300)
    if result.returncode not in {0, 2}:
        raise RuntimeError(f"Host launcher failed: {result.stderr[-2000:]}")
    report = json.loads(result.stdout)
    identity = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    assert report["tool_image"] == identity
    assert report["format_version"] == 1 and report["platform"].startswith("linux/")
    assert report["cpu_threads"] > 0 and report["free_storage_bytes"] > 0
    assert environment["CAF_HOST_TEST_CANARY"] not in result.stdout
    typer.echo("PASS: packaged host launcher, actual Linux probes, redacted report, no service changes")


if __name__ == "__main__":
    app()
