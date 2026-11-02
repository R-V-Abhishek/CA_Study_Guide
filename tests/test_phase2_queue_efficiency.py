"""The classification queue keeps its exact output while paging, filtering and batching in SQL."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from caf_db.engine import get_engine
from caf_db.models.classification import (
    ClassificationDispute,
    ClassificationRevision,
    QuestionPublication,
)
from test_phase5_api import BASE, clone, review_body
from test_phase5_publication import manifest, suggestion  # noqa: F401  (pytest fixtures)

GOLDEN = Path(__file__).parent / "fixtures" / "classification_queue_golden.json"
FILTERS = [
    {},
    {"limit": 3},
    {"limit": 2, "offset": 2},
    {"offset": 4},
    {"experimental": "true"},
    {"experimental": "false"},
    {"outcome": "needs_review"},
    {"outcome": "matched"},
    {"benchmark_only": "true"},
    {"disputed": "true"},
    {"disputed": "false", "limit": 3},
    {"ready": "true"},
    {"ready": "false", "limit": 3},
    {"ready": "false", "offset": 1, "limit": 2},
    {"paper_id": "no-such-paper"},
    {"blind": "true", "limit": 2},
]


@pytest.fixture
def populated(session, suggestion, authenticated_client):  # noqa: F811
    unresolved = [
        {
            **part,
            "outcome": "needs_review",
            "primary_node_id": None,
            "secondary_node_ids": [],
            "evidence": {},
        }
        for part in suggestion.mappings
    ]
    for index in range(5):
        clone(
            session,
            suggestion,
            question_id=f"{suggestion.question_id}.extra{index}",
            experimental=index % 2 == 1,
            mappings=unresolved if index % 3 == 0 else None,
        )
    client = authenticated_client(user_id=2, role="student")
    assert (
        client.post(f"{BASE}/{suggestion.id}/review", json=review_body(suggestion)).status_code
        == 200
    )
    revision = session.scalar(
        sa.select(ClassificationRevision).where(
            ClassificationRevision.question_id == suggestion.question_id
        )
    )
    session.add(
        ClassificationDispute(
            question_id=suggestion.question_id,
            revision_id=revision.id,
            actor_id=2,
            reason="Disputed",
        )
    )
    session.commit()
    return client


def normalize(rows):
    """Fixture node ids and hashes are random per run, so compare the deterministic review state."""
    return [
        dict(
            suggestion_revision_id=row["suggestion_revision_id"],
            question_id=row["question_id"],
            experimental=row["experimental"],
            stale=row["stale"],
            publication_ready=row["publication_ready"],
            blockers=[block["code"] for block in row["readiness_blockers"]],
            outcomes=[part["outcome"] for part in row["mappings"]],
            run_id=row["run_id"],
            publication_revision_id=row["publication_revision_id"],
            publication_suggestion_revision_id=row["publication_suggestion_revision_id"],
            published_outcomes=[part["outcome"] for part in row["published_mappings"]],
            verification_count=row["verification_count"],
            verified_by_me=row["verified_by_me"],
            dispute_status=row["dispute_status"],
            is_benchmark=row["is_benchmark"],
            blind=row["blind"],
            candidate_count=len(row["candidates"]),
            provenance_keys=sorted(row["provenance"]),
        )
        for row in rows
    ]


def test_queue_output_is_unchanged_for_every_filter(populated):
    actual = {
        json.dumps(params, sort_keys=True): normalize(populated.get(BASE, params=params).json())
        for params in FILTERS
    }
    if not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    for key in expected:
        assert actual[key] == expected[key], key


def test_queue_query_count_is_bounded_by_the_page(populated, session, suggestion):  # noqa: F811
    for index in range(20):
        clone(session, suggestion, question_id=f"{suggestion.question_id}.bulk{index}")
    counts = {}
    for limit in (5, 25):
        statements = []
        engine = get_engine("curation")
        listener = lambda connection, cursor, statement, *args: statements.append(statement)
        event.listen(engine, "before_cursor_execute", listener)
        try:
            assert len(populated.get(BASE, params={"limit": limit}).json()) == limit
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        counts[limit] = len(statements)
    # A fixed number of batched lookups for the page plus the per-row readiness gate.
    assert counts[25] - counts[5] <= 20 * 12, counts
    assert counts[5] <= 5 * 12 + 15, counts
