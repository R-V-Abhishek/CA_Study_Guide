"""Validate installation planning using real Compose rendering and synthetic artifacts."""

import json
from pathlib import Path
import sys

import pytest
from typer.testing import CliRunner

from caf_cli.host import app
from caf_cli.host_bundle import verify_archive
from test_host_backup import snapshot
from test_release_bundle import bundle_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify_production_compose import fixture, render


@pytest.fixture
def prepared(snapshot, tmp_path):
    bundle = bundle_fixture(tmp_path)
    manifest = verify_archive(bundle)
    values = fixture()
    values.update(CAF_IMAGE=manifest.application.reference, CAF_POSTGRES_IMAGE=manifest.postgres.reference,
                  CAF_REVISION=manifest.commit, CAF_PLATFORM=manifest.platform,
                  OIDC_CLIENT_SECRET="do-not-log$literal")
    rendered = render(values, tools=True)
    assert rendered.returncode == 0, rendered.stderr
    path = tmp_path / "rendered.json"
    path.write_text(rendered.stdout)
    output = tmp_path / "output"
    output.mkdir()
    return bundle, path, output


def invoke(prepared, snapshot, *extra):
    bundle, rendered, output = prepared
    return CliRunner().invoke(app, ["_install", "prepare", str(bundle), str(snapshot), str(rendered),
        str(output), "--destination", "/srv/caf", "--project", "caf", *extra])


def test_install_plan_pins_images_and_preserves_literal_credentials(prepared, snapshot):
    result = invoke(prepared, snapshot, "--allow-candidate")
    assert result.exit_code == 0, result.output or result.exception
    assert "do-not-log" not in result.output
    config = json.loads((prepared[2] / "compose.json").read_text())
    assert config["services"]["web"]["environment"]["OIDC_CLIENT_SECRET"] == "do-not-log$$literal"
    assert config["services"]["db"]["pull_policy"] == "never"
    assert all(mount["bind"]["create_host_path"] is False for service in config["services"].values()
               for mount in service["volumes"])
    receipt = json.loads((prepared[2] / "receipt.json").read_text())
    assert receipt["phase"] == "prepared" and receipt["database_revision"] == "0009_question_language"


def test_candidates_need_explicit_install_permission(prepared, snapshot):
    assert invoke(prepared, snapshot).exit_code != 0
    assert not (prepared[2] / "compose.json").exists()


@pytest.mark.parametrize("failure", ["password", "image", "storage", "schema", "protected"])
def test_invalid_inputs_do_not_produce_execution_configuration(prepared, snapshot, failure):
    configuration = json.loads(prepared[1].read_text())
    if failure == "password":
        configuration["services"]["admin"]["environment"]["PG_APP_PASSWORD"] = "short-secret"
    elif failure == "image":
        configuration["services"]["web"]["image"] = "caf:wrong"
    elif failure == "storage":
        configuration["services"]["web"]["volumes"][0]["source"] = "/etc"
    else:
        path = snapshot / "manifest.json"
        data = json.loads(path.read_text())
        if failure == "schema":
            data["database_revision"] = "unsupported"
        else:
            data["tables"] = {}
        path.write_text(json.dumps(data))
    prepared[1].write_text(json.dumps(configuration))
    result = invoke(prepared, snapshot, "--allow-candidate")
    assert result.exit_code != 0 and not (prepared[2] / "compose.json").exists()
    assert "short-secret" not in result.output
