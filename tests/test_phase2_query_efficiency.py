"""Dashboard and paper summaries keep their exact output while issuing a bounded number of queries."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from caf_db.engine import get_engine

GOLDEN = Path(__file__).parent / "fixtures" / "papers_dashboard_golden.json"
# Measured after batching; the per-paper loops that scaled with the six papers are gone.
QUERY_LIMIT = {"/api/v1/papers": 24, "/api/v1/dashboard": 36}


def leaves(client, paper_id):
    tree = client.get(f"/api/v1/papers/{paper_id}/tree").json()
    return [sub["id"] for chapter in tree["chapters"] for topic in chapter["topics"] for sub in topic["subtopics"]]


def capture(client):
    result = {}
    for path in ("/api/v1/papers", "/api/v1/dashboard"):
        result[path] = client.get(path).json()
    return result


@pytest.fixture
def progressed(authenticated_client):
    client = authenticated_client()
    for paper, statuses in (("s2023.P1", ["done", "done", "in_progress"]), ("s2023.P5", ["done"]), ("s2023.P3", ["in_progress"])):
        for node, status in zip(leaves(client, paper), statuses):
            assert client.put(f"/api/v1/subtopics/{node}/progress", json={"status": status}).status_code == 200
    return client


def normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def test_papers_and_dashboard_output_is_unchanged(progressed):
    actual = normalized(capture(progressed))
    if isinstance(actual["/api/v1/dashboard"], dict):
        for activity in actual["/api/v1/dashboard"]["recent_activity"]:
            activity.pop("at")  # wall-clock time of the fixture's own writes
    if not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    assert actual == json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("path", sorted(QUERY_LIMIT))
def test_query_count_does_not_grow_with_papers(progressed, path):
    statements = []
    engine = get_engine("student")
    listener = lambda connection, cursor, statement, *args: statements.append(statement)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert progressed.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) <= QUERY_LIMIT[path], f"{len(statements)} queries"
