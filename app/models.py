from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Each user has exactly one Immich base URL and API key
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    instances: Mapped[list["Instance"]] = relationship("Instance", back_populates="user")
    owned_groups: Mapped[list["SyncGroup"]] = relationship("SyncGroup", back_populates="owner")
    memberships: Mapped[list["GroupMember"]] = relationship("GroupMember", back_populates="user")


class SyncGroup(Base):
    __tablename__ = "sync_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship("User", back_populates="owned_groups")
    members: Mapped[list["GroupMember"]] = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    instances: Mapped[list["Instance"]] = relationship("Instance", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("sync_groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    group: Mapped["SyncGroup"] = relationship("SyncGroup", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="memberships")


class Instance(Base):
    __tablename__ = "instances"
    __table_args__ = (UniqueConstraint("sync_id", "user_id", name="uq_instance_user_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_id: Mapped[int] = mapped_column(ForeignKey("sync_groups.id"))
    label: Mapped[str] = mapped_column(String(200))
    album_id: Mapped[str] = mapped_column(String(200))
    size_limit_bytes: Mapped[int] = mapped_column(Integer, default=100 * 1024 * 1024)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship("User", back_populates="instances")
    group: Mapped["SyncGroup"] = relationship("SyncGroup", back_populates="instances")
    asset_presences: Mapped[list["AssetPresence"]] = relationship("AssetPresence", back_populates="instance")


class AssetHash(Base):
    __tablename__ = "asset_hashes"
    __table_args__ = (UniqueConstraint("sync_id", "checksum", name="uq_sync_checksum"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_id: Mapped[int] = mapped_column(ForeignKey("sync_groups.id"))
    checksum: Mapped[str] = mapped_column(String(256))
    original_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    presences: Mapped[list["AssetPresence"]] = relationship("AssetPresence", back_populates="asset_hash")


class AssetPresence(Base):
    __tablename__ = "asset_presences"
    __table_args__ = (UniqueConstraint("asset_hash_id", "instance_id", name="uq_hash_instance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_hash_id: Mapped[int] = mapped_column(ForeignKey("asset_hashes.id"))
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id"))
    remote_asset_id: Mapped[str] = mapped_column(String(256))
    in_album: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    asset_hash: Mapped["AssetHash"] = relationship("AssetHash", back_populates="presences")
    instance: Mapped["Instance"] = relationship("Instance", back_populates="asset_presences")

