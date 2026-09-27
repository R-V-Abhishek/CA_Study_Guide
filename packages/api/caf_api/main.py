"""FastAPI serving application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from caf_common.settings import get_settings
from caf_api.routes import router
from caf_api.curate import router as curate_router

settings = get_settings()

app = FastAPI(
    title="CA Final Study Companion API",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(curate_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env, "target_attempt": settings.app.target_attempt_id}


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
        file_path = CURATOR_DIST / full_path
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
        file_path = STUDENT_DIST / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(student_index)

