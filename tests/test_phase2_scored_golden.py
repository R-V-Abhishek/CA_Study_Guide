"""Papers and dashboard keep their exact output when a score run exists."""

import json
from pathlib import Path

from caf_l5.scoring import recompute_scores
from test_phase5_publication import suggestion  # noqa: F401  (pytest fixture)
from test_phase6_intelligence import manifest, reviewed_context  # noqa: F401  (pytest fixtures)

GOLDEN = Path(__file__).parent / "fixtures" / "papers_dashboard_scored_golden.json"


def normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def without_clock(value):
    """Drop wall-clock fields, which differ on every run, at any depth."""
    if isinstance(value, dict):
        return {k: without_clock(v) for k, v in value.items() if k not in {"computed_at", "at"}}
    if isinstance(value, list):
        return [without_clock(item) for item in value]
    return value


def test_scored_papers_and_dashboard_output_is_unchanged(
    session, reviewed_context, authenticated_client
):
    suggestion, target = reviewed_context
    run = recompute_scores(session, target, taxonomy_version_id=suggestion.taxonomy_version_id)
    client = authenticated_client(1, target=target)
    actual = {}
    for path in ("/api/v1/papers", "/api/v1/dashboard"):
        response = client.get(path)
        assert response.status_code == 200, response.text
        actual[path] = normalized(response.json())
    assert run.id and "score" in json.dumps(actual)
    actual = without_clock(actual)
    key = lambda row: (row["paper_id"], row["attempt_id"], row.get("source_family") or "")
    matrix = actual["/api/v1/dashboard"]["ingestion_coverage"]
    assert matrix == sorted(matrix, key=key), "the coverage matrix has a stable order"
    matrix.sort(key=key)
    # Fixture taxonomy nodes get random UUIDs, so only the names identify a preview item.
    for item in actual["/api/v1/dashboard"]["plan_preview"]:
        item.pop("node_id"), item.pop("chapter_id")
    if not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    assert actual == json.loads(GOLDEN.read_text())
