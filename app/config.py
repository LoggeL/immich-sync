from __future__ import annotations

from datetime import timedelta
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IMMICH_SYNC_", env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Immich Sync"
    secret_key: str = Field(default="change-me-secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = Field(default="sqlite:////workspace/data.db")
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # daily sync default time HH:MM
    default_sync_time: str = "00:00"


settings = Settings()


def get_access_token_timedelta() -> timedelta:
    return timedelta(minutes=settings.access_token_expire_minutes)

