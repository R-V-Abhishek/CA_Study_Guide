"""Build and score identities for diagnostics, without personal content."""

from functools import lru_cache
import os
from pathlib import Path
import subprocess

from caf_db.models.intel import ScoreRun


@lru_cache(maxsize=1)
def backend_revision() -> str:
    configured = os.environ.get('CAF_BACKEND_REVISION')
    if configured:
        return configured
    result = subprocess.run(
        ['git', 'rev-parse', '--short=12', 'HEAD'],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def score_run_identity(run: ScoreRun | None) -> dict | None:
    if run is None:
        return None
    return {
        'id': run.id,
        'version': run.scoring_version,
        'target_attempt_id': run.target_attempt_id,
        'taxonomy_version_id': run.taxonomy_version_id,
        'computed_at': run.finished_at,
    }
