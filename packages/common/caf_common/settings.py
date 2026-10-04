"""Typed configuration loader using pydantic-settings and TOML files."""

from pathlib import Path
import os
import tomllib
from typing import Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    env: str = "development"
    target_attempt_id: str = "2026-05"


class StorageSettings(BaseModel):
    data_dir: Path = Path("./data")
    blob_dir: Path = Path("./data/blobs")
    inbox_dir: Path = Path("./data/inbox")
    debug_dir: Path = Path("./data/debug")
    log_dir: Path = Path("./data/logs")
    backup_dir: Path = Path("./data/backups")


class DatabaseSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 5433
    database: str = "caf"
    user: str = "postgres"
    password: str = "postgres_dev_password"

    @property
    def url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class OCRSettings(BaseModel):
    enabled: bool = False
    language: str = 'eng'
    dpi: int = Field(default=300, ge=72, le=600)
    min_native_chars: int = Field(default=10, ge=1)
    tessdata: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OIDC_ISSUER: str | None = None
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    OIDC_REDIRECT_URI: str | None = None
    AUTH_PUBLIC_BASE_URL: str = "http://localhost:8000"
    AUTH_LOCAL_DEVELOPMENT: bool = False
    AUTH_ALLOWED_ORIGINS: str = "http://localhost:8000,http://localhost:5173,http://localhost:5174"

    # Overrides from environment
    DATABASE_URL: str | None = None
    GEMINI_API_KEY: str | None = None
    PG_SUPERUSER: str = "postgres"
    PG_SUPERUSER_PASSWORD: str = "postgres_dev_password"
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5433
    PG_DATABASE: str = "caf"
    CAF_ENV: str | None = None
    PG_APP_PASSWORD: str | None = None
    PG_CURATOR_PASSWORD: str | None = None
    PG_PIPELINE_PASSWORD: str | None = None
    PG_IDENTITY_PASSWORD: str | None = None
    PG_OPERATIONS_PASSWORD: str | None = None
    PG_BACKUP_PASSWORD: str | None = None
    STUDENT_DATABASE_URL: str | None = None
    IDENTITY_DATABASE_URL: str | None = None
    CURATION_DATABASE_URL: str | None = None
    OPERATIONS_DATABASE_URL: str | None = None
    PIPELINE_DATABASE_URL: str | None = None
    BACKUP_DATABASE_URL: str | None = None
    MIGRATION_DATABASE_URL: str | None = None

    app: AppSettings = Field(default_factory=AppSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)

    @classmethod
    def load(cls, config_dir: Path = Path("config")) -> "Settings":
        settings_toml = config_dir / "settings.toml"
        toml_data: dict[str, Any] = {}
        if settings_toml.exists():
            with open(settings_toml, "rb") as f:
                toml_data = tomllib.load(f)

        inst = cls(**toml_data)
        if inst.CAF_ENV:
            inst.app.env = inst.CAF_ENV
        if os.environ.get("CAF_TEST_MODE") == "1":
            from caf_common.db_safety import assert_safe_database
            if not inst.DATABASE_URL or not os.environ.get("CAF_TEST_STORAGE_ROOT"):
                raise RuntimeError("Test settings require harness database and storage")
            assert_safe_database(inst.DATABASE_URL)
            root = Path(os.environ["CAF_TEST_STORAGE_ROOT"])
            inst.storage = StorageSettings(**{
                name: root / name.removesuffix("_dir")
                for name in StorageSettings.model_fields
            })
            inst.GEMINI_API_KEY = None
            inst.app.env = "test"
        # Reconcile DB URL if explicitly passed or configured
        if inst.DATABASE_URL:
            # We preserve custom url
            pass
        elif inst.PG_HOST:
            inst.database.host = inst.PG_HOST
            inst.database.port = inst.PG_PORT
            inst.database.database = inst.PG_DATABASE
            inst.database.user = inst.PG_SUPERUSER
            inst.database.password = inst.PG_SUPERUSER_PASSWORD

        # Ensure directories exist
        inst.storage.blob_dir.mkdir(parents=True, exist_ok=True)
        inst.storage.inbox_dir.mkdir(parents=True, exist_ok=True)
        inst.storage.debug_dir.mkdir(parents=True, exist_ok=True)
        inst.storage.log_dir.mkdir(parents=True, exist_ok=True)
        inst.storage.backup_dir.mkdir(parents=True, exist_ok=True)

        return inst


_cached_settings: Settings | None = None


def get_settings() -> Settings:
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = Settings.load()
    return _cached_settings


def reset_settings() -> None:
    global _cached_settings
    _cached_settings = None
