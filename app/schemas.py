from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    label: str
    expires_at: Optional[datetime] = None


class GroupOut(BaseModel):
    id: int
    label: str
    owner_id: int
    active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class GroupDetailOut(GroupOut):
    instances: list["InstanceOut"] = []


class InstanceCreate(BaseModel):
    sync_id: int
    label: str
    base_url: str
    api_key: str
    album_id: str
    size_limit_bytes: int = Field(default=1024 * 1024 * 1024 * 1024)
    active: bool = True


class InstanceOut(BaseModel):
    id: int
    user_id: int
    sync_id: int
    label: str
    base_url: str
    album_id: str
    size_limit_bytes: int
    active: bool

    class Config:
        from_attributes = True


class ProgressPerInstance(BaseModel):
    missing: int
    done: int


class SyncProgress(BaseModel):
    status: str
    total: int
    done: int
    per_instance: dict[int, ProgressPerInstance] | dict
    oversized: dict[int, list[dict]] | dict

