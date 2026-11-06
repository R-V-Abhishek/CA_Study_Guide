"""Upgrade planning, snapshot gating and receipt merging use real bundle and Compose rendering."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest
from typer.testing import CliRunner

from caf_cli.host import app
from caf_cli.host_bundle import ImageRecord, verify_archive
from caf_cli.host_upgrade import finalize, verify_snapshot
from test_host_backup import snapshot  # noqa: F401  (pytest fixture)
from test_release_bundle import bundle_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify_production_compose import fixture, render

NEW_VERSION = {
    "version": "v0.3.0",
    "application": ImageRecord(
        reference="caf:v0.3.0-candidate-aaaaaaaaaaaa-amd64", image_id="sha256:" + "f" * 64
    ),
}


HEAD = "0010_bounds_and_indexes"  # the packaged migration head that every upgrade target must match


def release(tmp_path, name, **overrides):
    directory = tmp_path / name
    directory.mkdir()
    return bundle_fixture(
        directory, overrides={"required_schema": HEAD, "supported_schemas": [HEAD], **overrides}
    )


@pytest.fixture
def installation(tmp_path):
    installed = verify_archive(release(tmp_path, "installed"))
    return {
        "format_version": 1,
        "phase": "active",
        "project": "caf",
        "destination": "/srv/caf",
        "application": installed.model_dump(mode="json"),
        "database_revision": "0009_question_language",
        "release_directory": "/srv/caf/releases/install-aaaa",
        "bundle_sha256": "1" * 64,
    }


def rendered_for(tmp_path, bundle):
    manifest = verify_archive(bundle)
    values = fixture()
    values.update(
        CAF_IMAGE=manifest.application.reference,
        CAF_POSTGRES_IMAGE=manifest.postgres.reference,
        CAF_REVISION=manifest.commit,
        CAF_PLATFORM=manifest.platform,
        OIDC_CLIENT_SECRET="do-not-log$literal",
    )
    result = render(values, tools=True)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "rendered.json"
    path.write_text(result.stdout)
    return path


def plan(tmp_path, installation, bundle, schema="0009_question_language", *extra):
    (tmp_path / "installation.json").write_text(json.dumps(installation))
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    result = CliRunner().invoke(
        app,
        [
            "_upgrade",
            "prepare",
            str(bundle),
            str(tmp_path / "installation.json"),
            str(rendered_for(tmp_path, bundle)),
            str(output),
            "--installed-schema",
            schema,
            *extra,
        ],
    )
    return result, output


def test_upgrade_plan_pins_new_release_and_preserves_literal_credentials(tmp_path, installation):
    bundle = release(tmp_path, "new", **NEW_VERSION)
    result, output = plan(
        tmp_path, installation, bundle, "0009_question_language", "--allow-candidate"
    )
    assert result.exit_code == 0, result.output or result.exception
    assert "do-not-log" not in result.output
    config = json.loads((output / "compose.json").read_text())
    assert config["services"]["web"]["image"] == NEW_VERSION["application"].reference
    assert config["services"]["web"]["environment"]["OIDC_CLIENT_SECRET"] == "do-not-log$$literal"
    assert config["services"]["db"]["volumes"][0]["source"] == "/srv/caf/postgres"
    receipt = json.loads((output / "receipt.json").read_text())
    assert (receipt["phase"], receipt["from_version"], receipt["migration_required"]) == (
        "upgrade_prepared",
        "v0.2.0",
        True,
    )


def test_same_schema_upgrade_requires_no_migration(tmp_path, installation):
    result, output = plan(
        tmp_path, installation, release(tmp_path, "new", **NEW_VERSION), HEAD, "--allow-candidate"
    )
    assert result.exit_code == 0, result.output or result.exception
    assert json.loads((output / "receipt.json").read_text())["migration_required"] is False


def test_candidate_upgrades_to_the_final_build_of_its_version(tmp_path, installation):
    final = {
        "candidate": False,
        "application": ImageRecord(reference="caf:v0.2.0-amd64", image_id="sha256:" + "e" * 64),
    }
    result, output = plan(tmp_path, installation, release(tmp_path, "final", **final), HEAD)
    assert result.exit_code == 0, result.output or result.exception
    installation["application"] = verify_archive(
        release(tmp_path, "installed-final", **final)
    ).model_dump(mode="json")
    result, output = plan(
        tmp_path, installation, release(tmp_path, "again"), HEAD, "--allow-candidate"
    )
    assert result.exit_code != 0 and "not older" in str(result.exception)


@pytest.mark.parametrize(
    "failure", ["candidate", "same", "older", "platform", "postgres", "newer_schema", "inactive"]
)
def test_unsafe_upgrades_produce_no_execution_configuration(tmp_path, installation, failure):
    overrides = dict(NEW_VERSION)
    schema, extra = "0009_question_language", ["--allow-candidate"]
    if failure == "candidate":
        extra = []
    elif failure == "same":
        overrides = {}
    elif failure == "older":
        installation["application"]["version"] = "v0.9.0"
    elif failure == "platform":
        installation["application"]["platform"] = "linux/arm64"
    elif failure == "postgres":
        installation["application"]["postgres"]["image_id"] = "sha256:" + "9" * 64
    elif failure == "newer_schema":
        schema = "0099_from_the_future"
    else:
        installation["phase"] = "prepared"
    result, output = plan(
        tmp_path, installation, release(tmp_path, "new", **overrides), schema, *extra
    )
    assert result.exit_code != 0
    assert not (output / "compose.json").exists() and not (output / "receipt.json").exists()


def moment(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def test_snapshot_must_match_schema_and_postdate_the_maintenance_window(snapshot):
    report = verify_snapshot(
        snapshot,
        expected_schema="0009_question_language",
        not_before=moment("2026-10-20T09:00:00+00:00"),
    )
    assert report["file_integrity_verified"] is True and report["restore_verified"] is False
    named = verify_snapshot(
        snapshot,
        expected_schema="0009_question_language",
        not_before=moment("2026-10-20T09:00:00+00:00"),
        name="caf_20261020_100000_000000_deadbeef",
    )
    assert named["name"] == "caf_20261020_100000_000000_deadbeef"
    with pytest.raises(ValueError, match="predates"):
        verify_snapshot(
            snapshot,
            expected_schema="0009_question_language",
            not_before=moment("2026-10-20T11:00:00+00:00"),
        )
    with pytest.raises(ValueError, match="schema"):
        verify_snapshot(
            snapshot,
            expected_schema="0008_baseline_adoption",
            not_before=moment("2026-10-20T09:00:00+00:00"),
        )


def test_snapshot_missing_protected_tables_is_rejected(snapshot):
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["tables"].pop("app.note")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Protected tables"):
        verify_snapshot(
            snapshot,
            expected_schema="0009_question_language",
            not_before=moment("2026-10-20T09:00:00+00:00"),
        )


def test_finalize_retains_the_previous_release_and_snapshot(installation):
    upgrade = {
        "phase": "upgrade_prepared",
        "application": {"version": "v0.3.0"},
        "database_revision": "0008_baseline_adoption",
        "target_database_revision": "0009_question_language",
        "loaded_images": {"caf:new": "sha256:new"},
        "bundle_sha256": "2" * 64,
    }
    snapshot_report = {"name": "caf_20261101_000000_000000_deadbeef", "manifest_sha256": "3" * 64}
    merged = finalize(
        installation,
        upgrade,
        snapshot_report,
        schema="0009_question_language",
        release_directory="/srv/caf/releases/upgrade-bbbb",
    )
    assert merged["application"]["version"] == "v0.3.0" and merged["release_directory"].endswith(
        "upgrade-bbbb"
    )
    assert merged["previous"][0]["application"]["version"] == "v0.2.0"
    assert merged["previous"][0]["release_directory"] == "/srv/caf/releases/install-aaaa"
    assert merged["previous"][0]["snapshot"]["name"] == snapshot_report["name"]
    again = finalize(
        merged,
        {**upgrade, "database_revision": "0009_question_language"},
        snapshot_report,
        schema="0009_question_language",
        release_directory="/srv/caf/releases/upgrade-cccc",
    )
    assert len(again["previous"]) == 2


def test_finalize_rejects_unprepared_or_wrong_schema(installation):
    with pytest.raises(ValueError, match="verified, loaded"):
        finalize(
            installation, {"phase": "upgrade_prepared"}, {}, schema="x", release_directory="/x"
        )
    with pytest.raises(ValueError, match="required schema"):
        finalize(
            installation,
            {
                "phase": "upgrade_prepared",
                "loaded_images": {},
                "target_database_revision": "0009_question_language",
            },
            {},
            schema="0001_initial_schema",
            release_directory="/x",
        )
