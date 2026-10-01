"""Playwright-only server with an owned PostgreSQL container and synthetic data.

Never connects to the configured normal database. SIGTERM permits container cleanup.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import signal
import tempfile


def main():
    # Uvicorn replays shutdown signals after serving. Convert SIGTERM to an
    # exception so the surrounding contexts always stop the owned container.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    os.environ["CAF_TEST_MODE"] = "1"
    os.environ["CAF_TEST_DATABASE_ALLOWLIST"] = "[]"
    os.environ["GEMINI_API_KEY"] = ""
    for role in ("APP", "CURATOR", "PIPELINE"):
        os.environ[f"PG_{role}_PASSWORD"] = secrets.token_hex(16)

    from caf_common.postgres_sandbox import PostgresSandbox
    with tempfile.TemporaryDirectory(prefix="caf-browser-") as storage, PostgresSandbox("browser") as sandbox:
        os.environ["CAF_TEST_STORAGE_ROOT"] = storage
        os.environ["CAF_TEST_ARTIFACT_ROOT"] = storage
        os.environ["DATABASE_URL"] = sandbox.url().render_as_string(hide_password=False)
        os.environ["PG_HOST"] = "127.0.0.1"
        os.environ["PG_PORT"] = str(sandbox.port)
        os.environ["PG_DATABASE"] = "postgres"
        os.environ["CAF_BACKEND_REVISION"] = os.environ.get("VITE_BUILD_REVISION", "browser-harness")

        from alembic import command
        from alembic.config import Config
        from caf_db.engine import get_engine, get_session_factory, reset_database
        from caf_db.models.app import Progress, Settings, UserAccount
        from caf_db.models.ingest import Document, TagSuggestion, Unit, UnitAnswer
        from caf_db.models.intel import ScoreRun, SubtopicScore
        from caf_db.models.ops import Run
        from caf_db.models.ref import Node
        from caf_l0.loader import TaxonomyLoader
        from caf_l5.config import load_scoring_config
        import sqlalchemy as sa

        command.upgrade(Config("alembic.ini"), "head")
        with get_session_factory()() as db:
            loader = TaxonomyLoader()
            loader.apply(db, loader.plan())
            db.add(UserAccount(id=1, name="Browser fixture student"))
            db.flush()
            db.add(Settings(user_id=1, target_attempt_id="2026-05", hours_per_week=2, minutes_per_subtopic=45))
            db.add(Run(id=1, stage="browser-fixture", status="ok", stats={}))
            db.flush()
            nodes = db.scalars(sa.select(Node).where(Node.level == "subtopic", Node.paper_id == "s2023.P1").order_by(Node.id).limit(3)).all()
            config = load_scoring_config()
            run = ScoreRun(scoring_version=config.version, config_hash=config.config_hash,
                           config_snapshot=config.model_dump(), target_attempt_id="2026-05",
                           status="ok", is_current=True, shadow=False,
                           finished_at=datetime.now(timezone.utc))
            db.add(run)
            db.flush()
            for node in nodes:
                db.add(SubtopicScore(score_run_id=run.id, node_id=node.id, applicable=True,
                                     exam_score=7.5, practice_score=2, weight_prior=1,
                                     importance=.75, freq_hits=3, freq_window=5,
                                     exam_marks_total=10, exam_count=1, practice_count=1))
            old = datetime.now(timezone.utc) - timedelta(days=90)
            db.add(Progress(user_id=1, node_id=nodes[2].id, status="done", first_done_at=old, status_changed_at=old))
            doc = Document(sha256="b" * 64, blob_path=str(Path(storage) / "fixture.pdf"), bytes=100,
                           origin="manual", scheme_id="s2023", attempt_id="2024-05", paper_id="s2023.P1",
                           doc_type_id="suggested_answer", title="Synthetic browser fixture",
                           catalog_status="confirmed", extract_status="ok")
            db.add(doc)
            db.flush()
            unit = Unit(document_id=doc.id, extract_run_id=1, label_path="Q1.a", display_label="1(a)",
                        kind="part", is_gradable=True, marks=10, marks_source="explicit",
                        page_start=1, page_end=1, block_start="p1-b1", block_end="p1-b2",
                        question_text="Synthetic browser review question", text_origin="pdf",
                        fingerprint="b" * 40, parse_confidence="high", validation_flags=[],
                        classify_status="suggested", current=True)
            db.add(unit)
            db.flush()
            db.add(UnitAnswer(unit_id=unit.id, answer_document_id=doc.id,
                              answer_text="Synthetic answer. " * 500 + "FINAL ANSWER SENTINEL",
                              pairing_method="same_doc"))
            db.add(TagSuggestion(unit_id=unit.id, run_id=1, node_id=nodes[0].id, role="primary",
                                 method="anchor", bucket="A", evidence={"gist": "Synthetic fixture"}, is_shadow=False))
            db.commit()
            fixture = {"paper_id": "s2023.P1", "nodes": [{"id": n.id, "name": n.name} for n in nodes],
                       "unit_id": unit.id, "score_run_id": run.id}

        from caf_api.main import app
        from fastapi import FastAPI
        import uvicorn
        harness = FastAPI(docs_url=None, openapi_url=None)

        @harness.get("/__test/fixture")
        def test_fixture():
            return fixture

        @harness.post("/__test/reset")
        def reset_fixture():
            from caf_db.models.app import MockTest, Note, ProgressEvent, RevisionEvent
            from caf_db.models.core import Appearance, AppearanceTag, ChangeLog, Decision
            with get_session_factory()() as db:
                for model in (AppearanceTag, Appearance, Decision, ChangeLog,
                              ProgressEvent, RevisionEvent, Note, Progress, MockTest):
                    db.execute(sa.delete(model))
                db.execute(sa.update(Unit).values(classify_status="suggested"))
                db.add(Progress(user_id=1, node_id=fixture["nodes"][2]["id"], status="done",
                                first_done_at=old, status_changed_at=old))
                db.commit()
            return {"reset": True}

        harness.mount("/", app)
        try:
            uvicorn.run(harness, host="0.0.0.0", port=8765, log_level="warning")
        finally:
            reset_database()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass  # Expected managed-server shutdown, after context cleanup.
