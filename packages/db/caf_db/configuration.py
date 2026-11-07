"""Provision local named connections without exposing credentials in output."""

from pathlib import Path
import secrets

from sqlalchemy.engine import make_url

from caf_common.settings import get_settings, reset_settings
from caf_db.engine import ROLE_NAMES, database_url, reset_database
from caf_db.grants import ROLE_PASSWORDS


def configure_connections(env_file: Path = Path(".env")) -> list[str]:
    """Add missing passwords and connection URLs; preserve configured values."""
    settings = get_settings()
    values = settings.model_dump()
    admin_url = database_url("migration")
    additions = {}
    for operation, role in ROLE_NAMES.items():
        key = f"PG_{ROLE_PASSWORDS[role]}_PASSWORD"
        url_key = f"{operation.upper()}_DATABASE_URL"
        # `caf db grants` sets the role password from PG_*_PASSWORD, so a stored URL must agree with it.
        url_password = make_url(values[url_key]).password if values[url_key] else None
        if values[key] and url_password is not None and url_password != values[key]:
            raise RuntimeError(
                f"{url_key} does not use the password in {key}; reconcile them first"
            )
        password = values[key] or url_password or secrets.token_hex(24)
        if not values[key]:
            additions[key] = password
        if not values[url_key]:
            additions[url_key] = admin_url.set(username=role, password=password).render_as_string(
                hide_password=False
            )
    existing = env_file.read_text() if env_file.exists() else ""
    lines = existing.splitlines()
    found = set()
    for index, line in enumerate(lines):
        key = line.partition("=")[0]
        if key in additions:
            lines[index] = f"{key}={additions[key]}"
            found.add(key)
    lines.extend(f"{key}={value}" for key, value in additions.items() if key not in found)
    if additions:
        # The file holds role passwords: create it private and tighten an existing one.
        env_file.touch(mode=0o600)
        env_file.chmod(0o600)
        env_file.write_text("\n".join(lines) + "\n")
    reset_database()
    reset_settings()
    return list(additions)
