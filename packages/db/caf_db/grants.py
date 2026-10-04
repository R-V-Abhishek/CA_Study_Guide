"""Explicit database capabilities; no schema-wide default grants to request roles."""

from sqlalchemy import text
from caf_db.engine import get_engine
from caf_common.settings import get_settings

SCHEMAS = ("ref", "ingest", "core", "intel", "app", "ops")
PERSONAL = ("settings", "progress", "progress_event", "note", "revision_event", "mock_test", "study_session", "progress_migration")
IDENTITY = ("user_account", "invitation", "login_transaction", "auth_session")
ROLE_PASSWORDS = {
    "caf_app": "APP", "caf_identity": "IDENTITY", "caf_curator": "CURATOR",
    "caf_operations": "OPERATIONS", "caf_pipeline": "PIPELINE", "caf_backup": "BACKUP",
}


def apply_grants() -> None:
    """Replace legacy broad permissions with explicit, idempotent capabilities."""
    engine = get_engine("migration")
    settings = get_settings().model_dump()
    with engine.begin() as conn:
        tables = conn.execute(text("SELECT schemaname, tablename FROM pg_tables WHERE schemaname=ANY(:schemas)"), {"schemas": list(SCHEMAS)}).all()
        known = {f"{s}.{t}" for s, t in tables}
        quote = conn.dialect.identifier_preparer.quote

        def grant(role, privilege, names):
            for name in names:
                if name in known:
                    schema, table = name.split(".")
                    conn.execute(text(f"GRANT {privilege} ON TABLE {quote(schema)}.{quote(table)} TO {role}"))

        for role, suffix in ROLE_PASSWORDS.items():
            password = settings[f"PG_{suffix}_PASSWORD"]
            if not password:
                raise RuntimeError(f"PG_{suffix}_PASSWORD is required to provision roles")
            exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}).scalar()
            # PostgreSQL utility statements cannot bind password literals. Its
            # own quote_literal provides correct escaping without interpolation.
            literal = conn.execute(text("SELECT quote_literal(:password)"), {"password": password}).scalar_one()
            conn.execute(text(f"{'ALTER' if exists else 'CREATE'} ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {literal}"))
            memberships = conn.execute(text("SELECT parent.rolname FROM pg_auth_members m JOIN pg_roles child ON child.oid=m.member JOIN pg_roles parent ON parent.oid=m.roleid WHERE child.rolname=:role"), {"role": role}).scalars().all()
            for parent in memberships:
                conn.execute(text(f"REVOKE {quote(parent)} FROM {role}"))
            for schema in SCHEMAS:
                conn.execute(text(f"REVOKE ALL ON SCHEMA {schema} FROM {role}"))
                conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {role}"))
                conn.execute(text(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {role}"))
                conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON TABLES FROM {role}"))
                conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON SEQUENCES FROM {role}"))
            conn.execute(text(f"GRANT USAGE ON SCHEMA {', '.join(SCHEMAS)} TO {role}"))

        shared = [name for name in known if name.split('.')[0] in {"ref", "core", "intel"}]
        grant("caf_app", "SELECT", shared)
        grant("caf_app", "SELECT, INSERT, UPDATE, DELETE", [f"app.{t}" for t in PERSONAL])
        grant("caf_identity", "SELECT, INSERT, UPDATE, DELETE", [f"app.{t}" for t in (*IDENTITY, "settings")])
        grant("caf_identity", "SELECT", ["ref.paper", "ref.attempt"])
        grant("caf_curator", "SELECT", shared + [name for name in known if name.startswith("ingest.")])
        grant("caf_curator", "INSERT, UPDATE, DELETE", ["core.decision", "core.appearance", "core.appearance_tag", "core.change_log", "ingest.taxonomy_gap"])
        grant("caf_curator", "INSERT", ["ref.descriptor_revision", "ref.descriptor_approval"])
        grant("caf_curator", "INSERT", ["ingest.extraction_review"])
        if "app.user_account" in known:
            for role in ("caf_curator", "caf_operations"):
                conn.execute(text(f"GRANT SELECT (id,role,status) ON app.user_account TO {role}"))
        if "ingest.unit" in known:
            conn.execute(text("GRANT UPDATE (classify_status) ON ingest.unit TO caf_curator"))
        # Operational workers administer shared corpus/scoring, never profiles.
        operational = [name for name in known if name.split('.')[0] in {"ref", "ingest", "core", "intel", "ops"} and name != "ops.alembic_version"]
        grant("caf_operations", "SELECT, INSERT, UPDATE, DELETE", operational)
        grant("caf_pipeline", "SELECT", [name for name in known if name.startswith("ref.")])
        grant("caf_pipeline", "SELECT", ["core.appearance", "core.decision"])
        grant("caf_pipeline", "SELECT, INSERT, UPDATE, DELETE", [name for name in known if name.split('.')[0] in {"ingest", "ops"} and name != "ops.alembic_version"])
        grant("caf_backup", "SELECT", known)
        # information_schema.sequences omits GENERATED AS IDENTITY sequences.
        sequences = conn.execute(text("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname=ANY(:schemas)"), {"schemas": list(SCHEMAS)}).all()
        for schema, name in sequences:
            for role in ROLE_PASSWORDS:
                allowed = (
                    role == "caf_backup" or
                    role == "caf_app" and schema == "app" and name.removesuffix("_id_seq") in PERSONAL or
                    role == "caf_identity" and schema == "app" and name.removesuffix("_id_seq") in IDENTITY or
                    role == "caf_curator" and (schema == "core" or schema == "ref" and name == "descriptor_revision_id_seq" or schema == "ingest" and name == "extraction_review_id_seq") or
                    role == "caf_operations" and schema != "app" or
                    role == "caf_pipeline" and schema in {"ingest", "ops"}
                )
                if allowed:
                    privilege = "SELECT" if role == "caf_backup" else "USAGE, SELECT"
                    conn.execute(text(f"GRANT {privilege} ON SEQUENCE {quote(schema)}.{quote(name)} TO {role}"))
