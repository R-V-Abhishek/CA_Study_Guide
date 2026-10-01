"""Read-only PostgreSQL schema snapshots for migration/recovery comparison."""

from pathlib import Path
import re
from typing import Any

from sqlalchemy import Connection, text

SCHEMAS = ("app", "core", "ingest", "intel", "ops", "ref")


# pg_dump can distribute a varchar[] -> text[] cast over its constant
# elements. Match only homogeneous, unbounded varchar string literals; do
# not remove casts from arbitrary expressions, NULLs or other data types.
_VARCHAR_LITERAL = r"'(?:''|[^'])*'::character varying"
_ARRAY_TEXT_CAST = re.compile(
    r"(?P<quoted>E'(?:\\.|''|[^'\\])*'|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")"
    rf"|\(ARRAY\[(?P<items>{_VARCHAR_LITERAL}(?:, {_VARCHAR_LITERAL})*)\]\)::text\[\]"
)
_VARCHAR_ITEM = re.compile(_VARCHAR_LITERAL)


def canonical_constraint_definition(definition: str) -> str:
    """Normalize only PostgreSQL's equivalent constant varchar-array cast.

    Quoted SQL literals/identifiers are consumed separately so their contents
    cannot accidentally be rewritten. Column casts, literal values, typmods,
    operators, constraint names and all other structure remain significant.
    """
    def replace(match: re.Match[str]) -> str:
        if match.group("quoted") is not None:
            return match.group(0)
        items = _VARCHAR_ITEM.findall(match.group("items"))
        return "ARRAY[" + ", ".join(f"({item})::text" for item in items) + "]"

    return _ARRAY_TEXT_CAST.sub(replace, definition)


def canonical_constraints(constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**constraint, "definition": canonical_constraint_definition(constraint["definition"])}
        for constraint in constraints
    ]


def schema_snapshot(connection: Connection) -> dict[str, dict[str, Any]]:
    """Capture tables, columns, constraints and indexes without changing the DB.

    The Alembic bookkeeping table is excluded. Callers comparing a recovery
    checkpoint should use a fresh database migrated to the same revision.
    """
    tables = connection.execute(
        text("""
            SELECT n.nspname AS schema_name, c.relname AS table_name, c.oid
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r', 'p')
              AND NOT (n.nspname = 'ops' AND c.relname = 'alembic_version')
            ORDER BY n.nspname, c.relname
        """),
        {"schemas": list(SCHEMAS)},
    ).mappings()
    result = {}
    for table in tables:
        parameters = {"oid": table["oid"]}
        columns = connection.execute(
            text("""
                SELECT a.attname AS name,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS type,
                       a.attnotnull AS not_null,
                       pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS default,
                       a.attidentity AS identity, a.attgenerated AS generated
                FROM pg_catalog.pg_attribute a
                LEFT JOIN pg_catalog.pg_attrdef d
                  ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE a.attrelid = :oid AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """), parameters,
        ).mappings()
        constraints = connection.execute(
            text("""
                SELECT conname AS name, contype AS type,
                       pg_catalog.pg_get_constraintdef(oid, false) AS definition
                FROM pg_catalog.pg_constraint
                WHERE conrelid = :oid ORDER BY conname
            """), parameters,
        ).mappings()
        indexes = connection.execute(
            text("""
                SELECT c.relname AS name,
                       pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
                FROM pg_catalog.pg_index i
                JOIN pg_catalog.pg_class c ON c.oid = i.indexrelid
                WHERE i.indrelid = :oid ORDER BY c.relname
            """), parameters,
        ).mappings()
        result[f"{table['schema_name']}.{table['table_name']}"] = {
            "columns": [dict(row) for row in columns],
            "constraints": canonical_constraints([dict(row) for row in constraints]),
            "indexes": [dict(row) for row in indexes],
        }
    return result


def compare_schema_snapshots(
    expected: dict[str, dict[str, Any]], actual: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return machine-readable drift; an empty result means schemas agree."""
    differences: dict[str, Any] = {}
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    if missing:
        differences["missing_tables"] = missing
    if unexpected:
        differences["unexpected_tables"] = unexpected
    changed = {}
    for table in sorted(expected.keys() & actual.keys()):
        changes = {}
        for section in ("columns", "constraints", "indexes"):
            expected_section = expected[table][section]
            actual_section = actual[table][section]
            if section == "constraints":
                # Also accept historical snapshots created before normalization.
                expected_section = canonical_constraints(expected_section)
                actual_section = canonical_constraints(actual_section)
            if expected_section != actual_section:
                changes[section] = {
                    "expected": expected[table][section], "actual": actual[table][section]
                }
        if changes:
            changed[table] = changes
    if changed:
        differences["changed_tables"] = changed
    return differences



def migrated_schema_snapshot(connection: Connection, revision: str) -> dict[str, dict[str, Any]]:
    """Build the recorded revision in an empty disposable DB, then inspect it.

    The supplied connection is the sole migration target. Global settings and
    cached application connections remain untouched. Existing CAF relations
    are rejected so this helper cannot migrate an existing checkpoint/source.
    The caller owns destination creation and disposal.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from caf_common.db_safety import assert_safe_database

    assert_safe_database(connection.engine.url)
    if connection.dialect.name != "postgresql":
        raise ValueError("Migration baseline requires PostgreSQL")
    existing = connection.execute(
        text("""
            SELECT n.nspname, c.relname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(:schemas) AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
            LIMIT 1
        """),
        {"schemas": list(SCHEMAS)},
    ).first()
    if existing is not None:
        raise ValueError("Migration baseline destination already contains CAF relations")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    # Manifests must identify one concrete revision, never a moving head.
    resolved = script.get_revision(revision)
    if resolved is None or resolved.revision != revision:
        raise ValueError("Migration baseline requires a concrete recorded revision")
    config.attributes["connection"] = connection
    command.upgrade(config, revision)
    return schema_snapshot(connection)
