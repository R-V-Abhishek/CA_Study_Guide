"""Local preview restored from the real corpus; never writes to its source DB."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import signal
import tempfile

import sqlalchemy as sa
import typer

from caf_common.backup import create_backup, database_content, _pg_command
from caf_common.postgres_sandbox import PostgresSandbox
from caf_common.settings import get_settings, reset_settings
from caf_db.engine import reset_database


def main(port: int = 8788, database_port: int = 0):
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    source_settings = get_settings()
    if source_settings.app.env != "development" or os.environ.get("CAF_TEST_MODE") == "1":
        raise RuntimeError("Real-data preview requires the local development corpus")
    with tempfile.TemporaryDirectory(prefix="caf-real-preview-") as temporary:
        root = Path(temporary)
        # Existing backup machinery captures all tables from one read-only
        # snapshot and copies/verifies source files. No event is written back.
        print("Copying the real corpus and sources…", flush=True)
        backup = create_backup(backup_dir=root / "snapshot")
        manifest = json.loads(backup.manifest_file.read_text())
        with PostgresSandbox("real-preview", use_tmpfs=False, published_port=database_port) as sandbox:
            _pg_command("pg_restore", sandbox.url(), ["--exit-on-error", "--no-owner", "--no-acl", str(backup.dump_file)])
            engine = sa.create_engine(sandbox.url())
            with engine.connect() as connection:
                restored = database_content(connection)
                if restored != manifest["tables"]:
                    raise RuntimeError("Real preview restore differs from the source snapshot")
            engine.dispose()
            print(f"Verified {len(restored)} tables against source content digests.", flush=True)

            reset_database()
            reset_settings()
            os.environ["CAF_TEST_MODE"] = "1"
            os.environ["CAF_TEST_DATABASE_ALLOWLIST"] = "[]"
            sandbox.allow("postgres")
            os.environ["CAF_TEST_STORAGE_ROOT"] = str(root)
            os.environ["CAF_TEST_ARTIFACT_ROOT"] = str(root)
            # Settings' test storage convention removes the "_dir" suffix.
            (backup.dump_file.parent / "blobs").rename(root / "blob")
            os.environ["DATABASE_URL"] = sandbox.url().render_as_string(hide_password=False)
            os.environ["MIGRATION_DATABASE_URL"] = os.environ["DATABASE_URL"]
            for operation, suffix in {"student": "APP", "curation": "CURATOR", "identity": "IDENTITY",
                                      "operations": "OPERATIONS", "pipeline": "PIPELINE", "backup": "BACKUP"}.items():
                password = secrets.token_hex(24)
                os.environ[f"PG_{suffix}_PASSWORD"] = password
                username = "caf_curator" if operation == "curation" else "caf_app" if operation == "student" else "caf_" + operation
                os.environ[f"{operation.upper()}_DATABASE_URL"] = sandbox.url().set(username=username, password=password).render_as_string(hide_password=False)
            origin = f"http://127.0.0.1:{port}"
            os.environ["AUTH_PUBLIC_BASE_URL"] = origin
            os.environ["AUTH_ALLOWED_ORIGINS"] = origin
            os.environ["AUTH_LOCAL_DEVELOPMENT"] = "true"
            os.environ["GEMINI_API_KEY"] = ""
            for name in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI"):
                os.environ[name] = ""

            from caf_db.engine import get_engine, get_session_factory
            from caf_db.grants import apply_grants
            from caf_db.models.app import AuthSession, Invitation, LoginTransaction, UserAccount
            from caf_db.models.ingest import Document
            apply_grants()
            with get_engine().begin() as connection:
                now = datetime.now(timezone.utc)
                connection.execute(sa.update(AuthSession).values(revoked_at=now))
                connection.execute(sa.update(LoginTransaction).values(consumed_at=now))
                connection.execute(sa.update(Invitation).values(revoked_at=now))
                # Point cloned metadata at cloned files, preserving content hashes.
                for document_id, digest in connection.execute(sa.select(Document.id, Document.sha256)):
                    path = root / "blob" / digest[:2] / digest[2:4] / f"{digest}.pdf"
                    connection.execute(sa.update(Document).where(Document.id == document_id).values(blob_path=str(path)))
                account = connection.execute(sa.select(UserAccount.id).where(UserAccount.id == 1,
                    UserAccount.role == "administrator", UserAccount.status == "active")).scalar_one()

            from fastapi import FastAPI
            from fastapi.responses import HTMLResponse, RedirectResponse
            from caf_api import auth
            auth.SESSION_COOKIE = "caf_realpreview_session"
            auth.LOGIN_COOKIE = "caf_realpreview_login"
            from caf_api.main import app, lifespan
            harness = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)
            banner = ('<style>.workspace-sidebar,.curator-sidebar,.workspace-header,.curator-header{top:var(--preview-height,34px)}</style>'
                '<aside id="real-preview-banner" aria-label="Real data preview" style="position:sticky;top:0;z-index:40;padding:8px 12px;'
                'background:#fff3cd;color:#332600;font:14px system-ui"><strong>REAL CORPUS COPY</strong> · Edits stay in this preview. '
                '<a href="/__preview">Study / review</a></aside><script>new ResizeObserver(entries=>document.documentElement.style.setProperty('
                '"--preview-height",entries[0].target.getBoundingClientRect().height+"px")).observe(document.getElementById("real-preview-banner"));</script>')

            @harness.middleware("http")
            async def label_copy(request, call_next):
                response = await call_next(request)
                if response.headers.get("content-type", "").startswith("text/html"):
                    body = b"".join([chunk async for chunk in response.body_iterator]).decode()
                    headers = dict(response.headers)
                    headers.pop("content-length", None)
                    headers["Cache-Control"] = "no-store"
                    return HTMLResponse(re.sub(r"<body\b[^>]*>", lambda m: m[0] + banner, body, count=1),
                                        status_code=response.status_code, headers=headers)
                return response

            @harness.get("/__preview", response_class=HTMLResponse)
            def start():
                return ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Real corpus preview</title></head><body style="margin:0;font:17px system-ui"><main style="padding:24px">'
                    '<h1>Your actual study corpus</h1><p>This is a verified local copy of your existing database and PDFs, with no synthetic fixtures added. '
                    'Your existing administrator profile is preserved. Edits affect this disposable copy.</p>'
                    '<p>There are no published student questions yet. Review the actual sources, extraction revisions and classification suggestions in the curator app.</p>'
                    '<form method="post" action="/__preview/login?curator=false"><button>Open student app</button></form><br>'
                    '<form method="post" action="/__preview/login?curator=true"><button>Open actual review backlog</button></form></main></body></html>')

            @harness.post("/__preview/login")
            def login(curator: bool = False):
                with get_session_factory("identity")() as db:
                    token, _ = auth.create_session(db, account)
                    db.commit()
                response = RedirectResponse("/curator/classifications" if curator else "/", status_code=303)
                auth.set_cookie(response, auth.SESSION_COOKIE, token, 7 * 86400)
                return response

            harness.mount("/", app)
            print(f"Real-data preview ready: {origin}/__preview", flush=True)
            import uvicorn
            uvicorn.run(harness, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    cli = typer.Typer(pretty_exceptions_enable=False)
    cli.command()(main)
    try:
        cli()
    except KeyboardInterrupt:
        pass
