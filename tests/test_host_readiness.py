"""Readiness checks the actual restricted database role and required storage."""

from fastapi.testclient import TestClient
import sqlalchemy as sa

from caf_api.main import app
from caf_common.settings import get_settings


def test_readiness_uses_database_schema_and_storage(session, monkeypatch, tmp_path):
    client = TestClient(app)
    assert client.get("/api/v1/ready").json() == {"status": "ready"}
    session.execute(sa.text("UPDATE ops.alembic_version SET version_num='unsupported'"))
    session.commit()
    response = client.get("/api/v1/ready")
    assert response.status_code == 503 and response.json() == {"detail": "Service not ready"}
    session.execute(sa.text("UPDATE ops.alembic_version SET version_num='0009_question_language'"))
    session.commit()
    monkeypatch.setattr(get_settings().storage, "blob_dir", tmp_path / "missing")
    assert client.get("/api/v1/ready").status_code == 503
