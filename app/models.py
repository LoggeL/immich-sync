from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field


class SyncGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True, nullable=False)
    name: Optional[str] = None
    schedule_time: str = Field(default="02:00")  # HH:MM 24h
    expires_on: date | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Instance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sync_id: int = Field(foreign_key="syncgroup.id")
    label: str = Field(default="Instance")
    base_url: str
    api_key: str
    album_id: str
    size_limit_bytes: int = Field(default=100 * 1024 * 1024)  # 100 MB default
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AssetHash(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sync_id: int = Field(foreign_key="syncgroup.id")
    checksum: str = Field(index=True)
    original_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)


class AssetPresence(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    asset_hash_id: int = Field(foreign_key="assethash.id")
    instance_id: int = Field(foreign_key="instance.id")
    remote_asset_id: str
    in_album: bool = Field(default=True)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
