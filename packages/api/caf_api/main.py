"""FastAPI serving application."""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from caf_common.settings import get_settings
from caf_api.routes import router
from caf_api.curate import router as curate_router
from caf_api.auth import router as auth_router, allowed_origins, require_account, validate_auth_configuration
from caf_api.taxonomy import router as taxonomy_router
from caf_api.extraction import router as extraction_router
from caf_api.questions import router as questions_router
from caf_api.published_pages import router as published_pages_router
from caf_api.readiness import router as readiness_router
from caf_db.engine import get_engine, reset_database
from caf_api.security_logging import AUTH_ACCESS_FILTER

settings = get_settings()


@asynccontextmanager
async def lifespan(application):
    logging.getLogger("uvicorn.access").addFilter(AUTH_ACCESS_FILTER)
    validate_auth_configuration()
    for operation in ("student", "identity", "curation", "operations", "backup"):
        with get_engine(operation).connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    yield
    reset_database()

app = FastAPI(
    title="CA Final Study Companion API",
    version="1.0.0",
    docs_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router)
app.include_router(curate_router)
app.include_router(taxonomy_router)
app.include_router(extraction_router)
app.include_router(questions_router)
app.include_router(published_pages_router)
app.include_router(readiness_router)


@app.middleware("http")
async def private_response_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/auth/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    elif request.url.path.startswith(("/assets/", "/curator/assets/")) and response.status_code == 200:
        # Vite fingerprints these public build assets; a new build has new URLs.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(StarletteHTTPException)
async def authentication_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/auth/") and "text/html" in request.headers.get("accept", ""):
        messages = {
            "invite_required": ("Invitation required", "Open the invitation link supplied by your administrator."),
            "invitation_invalid": ("Invitation unavailable", "This invitation has expired, was revoked, or has already been used."),
            "invitation_email_mismatch": ("Invitation email mismatch", "Sign in using the invitation's email address and verify that address with your provider."),
            "account_disabled": ("Account disabled", "An administrator must restore access to your account."),
            "authentication_not_configured": ("Sign-in unavailable", "Hosted sign-in has not been configured yet."),
            "identity_provider_unavailable": ("Sign-in unavailable", "The server could not reach the sign-in provider. Check the server's internet connection and DNS, then try again."),
        }
        title, message = messages.get(str(exc.detail), ("Sign-in failed", "The sign-in request could not be verified. Start sign-in again."))
        return HTMLResponse(f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head><body><main><h1>{title}</h1><p>{message}</p><a href="/">Return to CA Final Prep</a></main></body></html>', status_code=exc.status_code)
    return await http_exception_handler(request, exc)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env, "target_attempt": settings.app.target_attempt_id}


@app.get("/api/v1/openapi.json", include_in_schema=False, dependencies=[Depends(require_account)])
def api_schema():
    return app.openapi()


# ==============================================================================
# SPA Static File Serving
# ==============================================================================
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STUDENT_DIST = Path("web/apps/student/dist")
CURATOR_DIST = Path("web/apps/curator/dist")

if CURATOR_DIST.exists():
    curator_index = CURATOR_DIST / "index.html"
    if (CURATOR_DIST / "assets").exists():
        app.mount("/curator/assets", StaticFiles(directory=CURATOR_DIST / "assets"), name="curator_assets")

    @app.get("/curator/{full_path:path}")
    async def serve_curator_spa(full_path: str = ""):
        file_path = (CURATOR_DIST / full_path).resolve()
        if not file_path.is_relative_to(CURATOR_DIST.resolve()):
            raise HTTPException(404)
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(curator_index)

    @app.get("/curator")
    async def serve_curator_root():
        return FileResponse(curator_index)


if STUDENT_DIST.exists():
    student_index = STUDENT_DIST / "index.html"
    if (STUDENT_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STUDENT_DIST / "assets"), name="student_assets")

    @app.get("/{full_path:path}")
    async def serve_student_spa(full_path: str = ""):
        if full_path.startswith(("api/", "auth/")):
            raise HTTPException(404)
        file_path = (STUDENT_DIST / full_path).resolve()
        if not file_path.is_relative_to(STUDENT_DIST.resolve()):
            raise HTTPException(404)
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(student_index)
