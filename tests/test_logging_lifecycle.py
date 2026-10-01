"""CLI capture must not leave pipeline loggers bound to closed streams."""

from typer.testing import CliRunner
from caf_cli.main import app
from caf_common.run_context import open_run
from caf_db.models.ops import Run


def test_pipeline_after_cli_capture(session):
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    with open_run("test-after-cli") as run:
        run_id = run.id
    assert session.get(Run, run_id).status == "ok"
