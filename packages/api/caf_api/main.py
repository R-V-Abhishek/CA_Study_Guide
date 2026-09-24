"""FastAPI serving application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from caf_common.settings import get_settings

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


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env, "target_attempt": settings.app.target_attempt_id}
