"""Database role management and idempotent permission grants."""

import os
from sqlalchemy import text
from caf_db.engine import get_engine


def apply_grants() -> None:
    """Create schemas, roles, and apply role-level permissions idempotently."""
    engine = get_engine()

    pipeline_pw = os.environ.get("PG_PIPELINE_PASSWORD", "pipeline_dev_password")
    curator_pw = os.environ.get("PG_CURATOR_PASSWORD", "curator_dev_password")
    app_pw = os.environ.get("PG_APP_PASSWORD", "app_dev_password")

    schemas = ["ref", "ingest", "core", "intel", "app", "ops"]

    with engine.begin() as conn:
        # Create schemas if not exist
        for s in schemas:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {s};"))

        # Create roles if not exist
        roles = {
            "caf_pipeline": pipeline_pw,
            "caf_curator": curator_pw,
            "caf_app": app_pw,
        }
        for role, pw in roles.items():
            res = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
            ).scalar()
            if not res:
                conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{pw}';"))
            else:
                conn.execute(text(f"ALTER ROLE {role} WITH PASSWORD '{pw}';"))

        # Grants for caf_pipeline: R ref; RW ingest, ops
        conn.execute(text("GRANT USAGE ON SCHEMA ref, ingest, ops TO caf_pipeline;"))
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA ref TO caf_pipeline;"))
        conn.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ingest, ops TO caf_pipeline;")
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ingest, ops TO caf_pipeline;"))
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA ingest, ops GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO caf_pipeline;"
            )
        )
        conn.execute(
            text("ALTER DEFAULT PRIVILEGES IN SCHEMA ingest, ops GRANT USAGE, SELECT ON SEQUENCES TO caf_pipeline;")
        )

        # Grants for caf_curator: R ref, ingest, app; RW core, intel, ops, ref
        conn.execute(text("GRANT USAGE ON SCHEMA ref, ingest, app, core, intel, ops TO caf_curator;"))
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA ingest, app TO caf_curator;"))
        conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, intel, ops, ref TO caf_curator;"
            )
        )
        conn.execute(
            text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, intel, ops, ref TO caf_curator;")
        )
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA core, intel, ops, ref GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO caf_curator;"
            )
        )
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA core, intel, ops, ref GRANT USAGE, SELECT ON SEQUENCES TO caf_curator;"
            )
        )

        # Grants for caf_app: R ref, core, intel; RW app
        conn.execute(text("GRANT USAGE ON SCHEMA ref, core, intel, app TO caf_app;"))
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA ref, core, intel TO caf_app;"))
        conn.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO caf_app;")
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO caf_app;"))
        conn.execute(
            text("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO caf_app;")
        )
        conn.execute(
            text("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO caf_app;")
        )
