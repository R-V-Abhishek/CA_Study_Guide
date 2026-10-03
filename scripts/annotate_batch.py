"""Batch suggestions use reviewed textbook candidates and recorded provenance."""

import typer
from caf_cli.classify import classify_run
from caf_common.logging import setup_logging


if __name__ == "__main__":
    setup_logging()
    typer.run(classify_run)
