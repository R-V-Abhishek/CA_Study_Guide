"""Regenerate the checked-in API document from FastAPI response contracts."""

import json
from pathlib import Path
from caf_api.main import app


def whole_numbers(value):
    """Write 1.0 as 1, as JavaScript does, so Release Please's version bump leaves the rest unchanged."""
    if isinstance(value, dict):
        return {key: whole_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [whole_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


Path("openapi.json").write_text(
    json.dumps(whole_numbers(app.openapi()), indent=2, ensure_ascii=False) + "\n"
)
