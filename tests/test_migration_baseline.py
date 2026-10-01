"""Compatibility checks for the frozen 0001 schema and recovery comparisons."""

import importlib.util
from io import StringIO
from pathlib import Path
import re

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from caf_db.models import Base
from caf_db.schema_baseline import compare_schema_snapshots, schema_snapshot


def load_initial_revision():
    path = Path(__file__).parents[1] / "packages/db/caf_db/alembic/versions/0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("frozen_initial", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ddl_statements(sql):
    statements = set()
    for statement in sql.split(";"):
        statement = statement.strip()
        if not statement.startswith(("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX")):
            continue
        if statement.startswith("CREATE TABLE"):
            # SQLAlchemy stores constraints in a set: declaration order is
            # irrelevant but column order remains part of the baseline.
            lines = [re.sub(r"\s+", " ", line).strip().rstrip(",") for line in statement.splitlines()]
            columns = []
            constraints = []
            for line in lines[1:-1]:
                target = constraints if line.startswith(
                    ("PRIMARY KEY", "CONSTRAINT", "UNIQUE", "FOREIGN KEY", "CHECK")
                ) else columns
                target.append(line)
            statements.add((lines[0], tuple(columns), tuple(sorted(constraints)), lines[-1]))
        else:
            statements.add(re.sub(r"\s+", " ", statement))
    return statements


def test_frozen_revision_matches_original_orm_schema():
    """Compile both baselines on PostgreSQL, including constraints and indexes."""
    revision = load_initial_revision()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    revision.op = Operations(context)
    revision.upgrade()
    dialect = postgresql.dialect()
    expected = []
    for table in Base.metadata.sorted_tables:
        expected.append(str(CreateTable(table).compile(dialect=dialect)))
        expected.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes)
    assert ddl_statements(output.getvalue()) == ddl_statements(";".join(expected))
    assert revision.revision == "0001_initial_schema"
    source = Path(revision.__file__).read_text()
    assert "caf_db.models" not in source
    assert "metadata.create_all" not in source


def test_schema_snapshot_reports_missing_and_changed_structure():
    table = {"columns": [{"name": "id", "type": "bigint"}], "constraints": [], "indexes": []}
    expected = {"core.appearance": table, "app.note": table}
    changed = {**table, "indexes": [{"name": "new_index"}]}
    actual = {"core.appearance": changed, "app.extra": table}
    drift = compare_schema_snapshots(expected, actual)
    assert drift["missing_tables"] == ["app.note"]
    assert drift["unexpected_tables"] == ["app.extra"]
    assert set(drift["changed_tables"]["core.appearance"]) == {"indexes"}
    assert compare_schema_snapshots(expected, expected) == {}


def test_fresh_migrated_database_has_complete_baseline():
    from alembic.autogenerate import compare_metadata
    from caf_db.engine import get_engine

    with get_engine().connect() as connection:
        snapshot = schema_snapshot(connection)
        assert set(snapshot) == set(Base.metadata.tables)
        context = MigrationContext.configure(
            connection,
            opts={
                "include_schemas": True,
                "include_object": lambda obj, name, kind, reflected, compare_to: not (
                    kind == "table" and name == "alembic_version"
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []
        for key, table in Base.metadata.tables.items():
            assert len(snapshot[key]["columns"]) == len(table.columns)
            assert len(snapshot[key]["constraints"]) == len(table.constraints)
            # PostgreSQL adds indexes for PK and unique constraints.
            assert len(snapshot[key]["indexes"]) >= len(table.indexes)


def test_varchar_array_cast_dump_restore_is_equivalent_without_hiding_drift():
    from caf_db.schema_baseline import canonical_constraint_definition

    original = (
        "CHECK (((bucket)::text = ANY ((ARRAY['A'::character varying, "
        "'B'::character varying, 'C'::character varying, 'D'::character varying])::text[])))"
    )
    restored = (
        "CHECK (((bucket)::text = ANY (ARRAY[('A'::character varying)::text, "
        "('B'::character varying)::text, ('C'::character varying)::text, "
        "('D'::character varying)::text])))"
    )
    assert canonical_constraint_definition(original) == restored
    assert canonical_constraint_definition(restored) == restored

    def snapshot(definition, name="check_suggestion_bucket"):
        return {"ingest.tag_suggestion": {
            "columns": [], "indexes": [],
            "constraints": [{"name": name, "type": "c", "definition": definition}],
        }}

    assert compare_schema_snapshots(snapshot(original), snapshot(restored)) == {}
    for changed in (
        restored.replace("'D'", "'E'"),
        restored.replace("ANY", "ALL"),
        restored.replace("(bucket)::text", "(bucket)::character varying"),
        restored.replace("character varying", "character varying(1)"),
        restored.replace("::text", "::bpchar"),
    ):
        assert compare_schema_snapshots(snapshot(original), snapshot(changed))
    assert compare_schema_snapshots(snapshot(original), snapshot(restored, "different_name"))

    # Values containing apostrophes or commas remain byte-for-byte intact.
    escaped = "CHECK (value = ANY ((ARRAY['O''Brien, Inc.'::character varying])::text[]))"
    expected = "CHECK (value = ANY (ARRAY[('O''Brien, Inc.'::character varying)::text]))"
    assert canonical_constraint_definition(escaped) == expected
    # SQL-looking text inside a string is data, not an array expression.
    quoted = "CHECK (note = '(ARRAY[''A''::character varying])::text[]')"
    assert canonical_constraint_definition(quoted) == quoted
    typmod = "CHECK (value = ANY ((ARRAY['A'::character varying(1)])::text[]))"
    assert canonical_constraint_definition(typmod) == typmod


def test_supplied_connection_migration_baseline_isolated_from_settings(isolated_database, monkeypatch):
    from uuid import uuid4
    import pytest
    import sqlalchemy as sa
    import caf_common.settings
    from caf_db.engine import get_engine
    from caf_db.schema_baseline import migrated_schema_snapshot

    database = f"caf_baseline_{uuid4().hex}"
    isolated_database.allow(database)
    admin = sa.create_engine(isolated_database.url(), isolation_level="AUTOCOMMIT")
    destination = sa.create_engine(isolated_database.url(database))
    source = get_engine()
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{database}"'))
            created = True
        with source.connect() as connection:
            before = schema_snapshot(connection)

        def settings_forbidden():
            raise AssertionError("Supplied migration connection must not resolve application settings")

        monkeypatch.setattr(caf_common.settings, "get_settings", settings_forbidden)
        with destination.connect() as connection:
            baseline = migrated_schema_snapshot(connection, "0001_initial_schema")
            assert compare_schema_snapshots(baseline, before) == {}
            with pytest.raises(ValueError, match="already contains"):
                migrated_schema_snapshot(connection, "0001_initial_schema")
        with source.connect() as connection:
            assert schema_snapshot(connection) == before
    finally:
        source.dispose()
        destination.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(sa.text(f'DROP DATABASE "{database}"'))
        admin.dispose()
