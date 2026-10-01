"""Alembic environment configuration."""

from contextlib import nullcontext
from logging.config import fileConfig
from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from caf_common.settings import get_settings
from caf_common.db_safety import assert_safe_database
from caf_db.models.base import Base
# Import all models to ensure they register on metadata
import caf_db.models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

SCHEMAS = ["ref", "ingest", "core", "intel", "app", "ops"]


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        schema = getattr(object, "schema", None)
        return schema in SCHEMAS
    return True


def run_migrations_offline() -> None:
    settings = get_settings()
    url = settings.DATABASE_URL or settings.database.url
    assert_safe_database(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema="ops",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_on_connection(connection) -> None:
    assert_safe_database(connection.engine.url)
    transaction = nullcontext() if connection.in_transaction() else connection.begin()
    with transaction:
        for schema in SCHEMAS:
            connection.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema="ops",
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        # Recovery drills use an explicitly owned disposable destination.
        # Do not resolve application settings or open another connection.
        run_migrations_on_connection(supplied_connection)
        return

    settings = get_settings()
    url = settings.DATABASE_URL or settings.database.url
    assert_safe_database(url)
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            run_migrations_on_connection(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
