"""Regenerate the checked-in API document from FastAPI response contracts."""

import json
from pathlib import Path
from caf_api.main import app

Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")
