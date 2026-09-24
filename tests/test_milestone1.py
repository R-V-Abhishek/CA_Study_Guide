"""Milestone 1 End-to-End Verification Test."""

import pytest
from fastapi.testclient import TestClient
from caf_api.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["target_attempt"] == "2026-05"


def test_list_papers():
    res = client.get("/api/v1/papers")
    assert res.status_code == 200
    papers = res.json()
    assert len(papers) == 6
    codes = [p["code"] for p in papers]
    assert codes == ["P1", "P2", "P3", "P4", "P5", "P6"]
    for p in papers:
        assert p["total_subtopics"] > 0


def test_paper_tree():
    res = client.get("/api/v1/papers/s2023.P1/tree")
    assert res.status_code == 200
    tree = res.json()
    assert tree["paper_id"] == "s2023.P1"
    assert len(tree["chapters"]) > 0

    first_ch = tree["chapters"][0]
    assert len(first_ch["topics"]) > 0
    first_top = first_ch["topics"][0]
    assert len(first_top["subtopics"]) > 0

    first_sub = first_top["subtopics"][0]
    assert first_sub["id"].startswith("P1-")
    assert first_sub["status"] in ["not_started", "in_progress", "done"]


def test_subtopic_progress_and_notes():
    # 1. Fetch tree to get a valid subtopic
    res = client.get("/api/v1/papers/s2023.P1/tree")
    tree = res.json()
    target_sub = tree["chapters"][0]["topics"][0]["subtopics"][0]
    sid = target_sub["id"]

    # 2. Update progress to 'in_progress'
    p_res = client.put(f"/api/v1/subtopics/{sid}/progress", json={"status": "in_progress"})
    assert p_res.status_code == 200
    assert p_res.json()["status"] == "in_progress"

    # 3. Add personal notes
    n_res = client.put(f"/api/v1/subtopics/{sid}/notes", json={"notes": "Reviewed core Ind AS definitions"})
    assert n_res.status_code == 200
    assert n_res.json()["notes"] == "Reviewed core Ind AS definitions"

    # 4. Mark as 'done'
    d_res = client.put(f"/api/v1/subtopics/{sid}/progress", json={"status": "done"})
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "done"

    # 5. Fetch subtopic detail
    detail_res = client.get(f"/api/v1/subtopics/{sid}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == sid
    assert detail["status"] == "done"
    assert detail["notes"] == "Reviewed core Ind AS definitions"
    assert detail["chapter"] is not None
    assert detail["weightage"] is not None


def test_dashboard():
    res = client.get("/api/v1/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["total_subtopics"] > 0
    assert data["done_subtopics"] >= 1
    assert len(data["recent_activity"]) >= 1
    recent = data["recent_activity"][0]
    assert "node_name" in recent
    assert "paper_code" in recent
