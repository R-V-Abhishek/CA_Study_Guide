#!/bin/sh
# No database, credentials, host mounts, or published ports are used.
set -eu
image=${1:?Usage: sh deploy/verify-image.sh IMAGE}
docker run --rm -i --network none --entrypoint python "$image" - <<'PY'
import importlib
import os
from pathlib import Path
import subprocess
import sys

assert sys.version_info[:2] == (3, 12)
assert os.getuid() == 10001
for module in (
    "caf_contracts", "caf_common", "caf_db", "caf_l0", "caf_l1", "caf_l2",
    "caf_l3", "caf_l4", "caf_l5", "caf_cli", "caf_api",
):
    importlib.import_module(module)
for path in (".env", ".git", "data", "web/node_modules"):
    assert not Path(path).exists(), path
for interface in ("student", "curator"):
    root = Path(f"web/apps/{interface}/dist")
    assert (root / "index.html").is_file()
    assert list((root / "assets").glob("*.js"))
assert list(Path("packages/db/caf_db/alembic/versions").glob("*.py"))
for name in ("scoring", "depth", "sources", "models"):
    assert Path(f"config/{name}.toml").is_file(), f"Missing runtime config: {name}"
from caf_common.settings import get_settings
settings = get_settings()
assert settings.app.env == "production"
assert not settings.AUTH_LOCAL_DEVELOPMENT
assert not settings.GEMINI_API_KEY
assert not os.environ.get("OPENROUTER_API_KEY")
assert settings.storage.data_dir == Path("/srv/caf/data")
probe = settings.storage.data_dir / ".packaging-write-check"
probe.write_text("ok")
probe.unlink()
importlib.import_module("caf_api.main")
from caf_api.auth import validate_auth_configuration
try:
    validate_auth_configuration()
except RuntimeError as error:
    assert "OIDC" in str(error), str(error)
else:
    raise AssertionError("Production must reject missing authentication configuration")
for command in (["caf", "--help"], ["caf-host", "--help"], ["caf", "intel", "worker", "--help"],
                ["alembic", "heads"], ["tesseract", "--version"], ["pg_dump", "--version"]):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr or result.stdout
    print(f"PASS: {' '.join(command)}", flush=True)
dump_version = subprocess.check_output(["pg_dump", "--version"], text=True)
assert " 16." in dump_version, dump_version
print("PASS: non-root Python 3.12, both UIs, migrations, CLI/worker, OCR, PostgreSQL client,")
print("      writable storage, production auth guard, no bundled local data or AI credentials.")
PY
