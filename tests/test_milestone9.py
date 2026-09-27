"""Test suite for Milestone 9: UI Foundation and Student App Core."""

import pytest
from fastapi.testclient import TestClient

from caf_api.main import app as api_app
from caf_db.engine import get_session_factory
from caf_db.models.ref import Node, Paper


@pytest.fixture
def client():
    return TestClient(api_app)


def test_student_spa_serving_and_fallback(client):
    """Verify that student SPA serves index.html at root and deep routes via HTML5 fallback."""
    # Root route
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "text/html" in res_root.headers.get("content-type", "")
    assert "CA Final" in res_root.text

    # Deep SPA route (fallback to index.html)
    res_papers = client.get("/papers")
    assert res_papers.status_code == 200
    assert "text/html" in res_papers.headers.get("content-type", "")
    assert "CA Final" in res_papers.text

    # Subtopic deep route
    res_deep = client.get("/papers/P1/some-node-id")
    assert res_deep.status_code == 200
    assert "text/html" in res_deep.headers.get("content-type", "")

    # Phase 3 Study Feature routes
    for path in ["/plan", "/revision", "/progress", "/mock"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "CA Final" in res.text


def test_curator_spa_serving_and_fallback(client):
    """Verify that curator SPA serves index.html at /curator and deep routes."""
    res_curator_root = client.get("/curator")
    assert res_curator_root.status_code == 200
    assert "text/html" in res_curator_root.headers.get("content-type", "")
    assert "Curator" in res_curator_root.text

    res_curator_queue = client.get("/curator/queue")
    assert res_curator_queue.status_code == 200
    assert "text/html" in res_curator_queue.headers.get("content-type", "")


def test_api_routes_not_shadowed_by_spa(client):
    """Verify that /api/v1/* routes return JSON responses and are never shadowed by HTML fallback."""
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.headers.get("content-type") == "application/json"
    data = res_health.json()
    assert data["status"] == "ok"

    res_dash = client.get("/api/v1/dashboard")
    assert res_dash.status_code == 200
    assert res_dash.headers.get("content-type") == "application/json"
    dash_data = res_dash.json()
    assert "target_attempt" in dash_data
    assert "overall_progress_pct" in dash_data

    res_papers = client.get("/api/v1/papers")
    assert res_papers.status_code == 200
    assert res_papers.headers.get("content-type") == "application/json"
    assert isinstance(res_papers.json(), list)


def test_decision_d2_student_api_no_content_leak(client):
    """Verify Decision D2: Student API endpoints NEVER return question_text or answer_text."""
    factory = get_session_factory()
    with factory() as session:
        # Find any active subtopic
        subtopic = session.query(Node).filter(Node.level == "subtopic").first()
        if not subtopic:
            pytest.skip("No subtopics in database")

        node_id = subtopic.id

    res = client.get(f"/api/v1/subtopics/{node_id}")
    assert res.status_code == 200
    data = res.json()

    # Verify root fields
    assert "question_text" not in data
    assert "answer_text" not in data

    # Verify appearance summaries
    appearances = data.get("appearances", [])
    for app_item in appearances:
        assert "question_text" not in app_item, "Violation of Decision D2: question_text leaked in student API!"
        assert "answer_text" not in app_item, "Violation of Decision D2: answer_text leaked in student API!"
