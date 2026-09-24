"""Typed configuration loader using pydantic-settings and TOML files."""

from pathlib import Path
import tomllib
from typing import Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    env: str = "development"
    user_id: int = 1
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Overrides from environment
    DATABASE_URL: str | None = None
    GEMINI_API_KEY: str | None = None
    PG_SUPERUSER: str = "postgres"
    PG_SUPERUSER_PASSWORD: str = "postgres_dev_password"
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5433
    PG_DATABASE: str = "caf"

    app: AppSettings = Field(default_factory=AppSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    @classmethod
    def load(cls, config_dir: Path = Path("config")) -> "Settings":
        settings_toml = config_dir / "settings.toml"
        toml_data: dict[str, Any] = {}
        if settings_toml.exists():
            with open(settings_toml, "rb") as f:
                toml_data = tomllib.load(f)

        inst = cls(**toml_data)
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
