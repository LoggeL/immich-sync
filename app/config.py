from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IMMICH_SYNC_", env_file=".env", env_file_encoding="utf-8")

    database_url: str = Field(default=f"sqlite:///{(Path(__file__).resolve().parent.parent / 'immich_sync.db').as_posix()}")
    secret_key: str = Field(default="change-me")
    default_sync_time: str = Field(default="02:00")  # HH:MM 24h


settings = Settings()

