from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import schemas
from .auth import authenticate_user, create_access_token, get_current_user, get_password_hash
from .db import get_session
from .models import GroupMember, Instance, SyncGroup, User
from .sync_service import SyncService
from .immich_client import ImmichClient


router = APIRouter(prefix="/api")

sync_service = SyncService()


@router.post("/auth/register", response_model=schemas.UserOut)
def register(user_in: schemas.UserCreate) -> schemas.UserOut:
    with get_session() as session:
        existing = session.query(User).filter(User.username == user_in.username).one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        user = User(username=user_in.username, hashed_password=get_password_hash(user_in.password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user  # type: ignore[return-value]


@router.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> schemas.Token:  # noqa: B008
    with get_session() as session:
        user = authenticate_user(session, form_data.username, form_data.password)
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        token = create_access_token(subject=user.username)
        return schemas.Token(access_token=token)


@router.post("/auth/login_json", response_model=schemas.Token)
def login_json(body: Dict[str, str]) -> schemas.Token:
    username = body.get("username", "")
    password = body.get("password", "")
    with get_session() as session:
        user = authenticate_user(session, username, password)
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        token = create_access_token(subject=user.username)
        return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: User = Depends(get_current_user)) -> schemas.UserOut:  # noqa: B008
    return current_user  # type: ignore[return-value]


# User Immich settings
@router.get("/settings/immich", response_model=schemas.ImmichSettings)
def get_settings(current_user: User = Depends(get_current_user)) -> schemas.ImmichSettings:  # noqa: B008
    if not current_user.base_url or not current_user.api_key:
        raise HTTPException(status_code=404, detail="Settings not set")
    return schemas.ImmichSettings(base_url=current_user.base_url, api_key=current_user.api_key)


@router.post("/settings/immich", response_model=schemas.ImmichSettings)
async def set_settings(settings_in: schemas.ImmichSettings, current_user: User = Depends(get_current_user)) -> schemas.ImmichSettings:  # noqa: B008
    # Validate against Immich API: can we list albums?
    client = ImmichClient(settings_in.base_url, settings_in.api_key)
    ok, _ = await client.list_albums()
    if not ok:
        raise HTTPException(status_code=400, detail="Could not validate Immich credentials")
    with get_session() as session:
        user = session.get(User, current_user.id)
        assert user is not None
        user.base_url = settings_in.base_url
        user.api_key = settings_in.api_key
        session.commit()
    return settings_in


# Groups
@router.post("/groups", response_model=schemas.GroupOut)
def create_group(group_in: schemas.GroupCreate, current_user: User = Depends(get_current_user)) -> schemas.GroupOut:  # noqa: B008
    with get_session() as session:
        # Validate expiry: must be in the future and <= 6 months from now
        now = datetime.utcnow()
        max_expiry = now.replace(microsecond=0)
        # Approx 6 months = 183 days
        from datetime import timedelta
        if group_in.expires_at <= now or group_in.expires_at > now + timedelta(days=183):
            raise HTTPException(status_code=400, detail="Expiry must be within 6 months and in the future")
        group = SyncGroup(label=group_in.label, owner_id=current_user.id, expires_at=group_in.expires_at)
        session.add(group)
        session.commit()
        session.refresh(group)
        # owner joins as member
        gm = GroupMember(group_id=group.id, user_id=current_user.id)
        session.add(gm)
        session.commit()
        return group  # type: ignore[return-value]


@router.get("/groups", response_model=List[schemas.GroupOut])
def list_groups(current_user: User = Depends(get_current_user)) -> List[schemas.GroupOut]:  # noqa: B008
    with get_session() as session:
        groups = (
            session.query(SyncGroup)
            .join(GroupMember, GroupMember.group_id == SyncGroup.id)
            .filter(GroupMember.user_id == current_user.id)
            .all()
        )
        return groups  # type: ignore[return-value]


@router.get("/groups/{group_id}", response_model=schemas.GroupDetailOut)
def get_group(group_id: int, current_user: User = Depends(get_current_user)) -> schemas.GroupDetailOut:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        is_member = session.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).count() > 0
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")
        rows = (
            session.query(Instance, User)
            .join(User, User.id == Instance.user_id)
            .filter(Instance.sync_id == group.id)
            .all()
        )
        instances = [
            schemas.InstanceOut(
                id=i.id,
                user_id=i.user_id,
                sync_id=i.sync_id,
                album_id=i.album_id,
                size_limit_bytes=i.size_limit_bytes,
                active=i.active,
                username=u.username,
                base_url=u.base_url,
            )
            for (i, u) in rows
        ]
        # members
        memb_rows = (
            session.query(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .filter(GroupMember.group_id == group.id)
            .all()
        )
        members = [schemas.UserOut.model_validate(u) for u in memb_rows]
        return schemas.GroupDetailOut(
            id=group.id,
            label=group.label,
            owner_id=group.owner_id,
            active=group.active,
            expires_at=group.expires_at,
            created_at=group.created_at,
            instances=instances,
            members=members,
        )


@router.post("/groups/{group_id}/members/{user_id}")
def add_member(group_id: int, user_id: int, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        if group.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only owner can add members")
        exists = session.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id).one_or_none()
        if exists:
            return {"status": "ok"}
        gm = GroupMember(group_id=group_id, user_id=user_id)
        session.add(gm)
        session.commit()
        return {"status": "ok"}


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_member(group_id: int, user_id: int, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        if group.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only owner can remove members")
        gm = session.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id).one_or_none()
        if not gm:
            return {"status": "ok"}
        session.delete(gm)
        session.commit()
        return {"status": "ok"}


@router.post("/groups/{group_id}/members")
def add_member_by_username(group_id: int, body: Dict[str, str], current_user: User = Depends(get_current_user)) -> Dict[str, Any]:  # noqa: B008
    username = (body.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        if group.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only owner can add members")
        user = session.query(User).filter(User.username == username).one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        exists = session.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user.id).one_or_none()
        if exists:
            return {"status": "ok"}
        gm = GroupMember(group_id=group_id, user_id=user.id)
        session.add(gm)
        session.commit()
        return {"status": "ok"}


@router.patch("/groups/{group_id}", response_model=schemas.GroupOut)
def update_group(group_id: int, body: schemas.GroupUpdate, current_user: User = Depends(get_current_user)) -> schemas.GroupOut:  # noqa: B008
    from datetime import timedelta
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        if group.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only owner can update group")
        if body.label is not None:
            group.label = body.label
        if body.expires_at is not None:
            now = datetime.utcnow()
            if body.expires_at <= now or body.expires_at > now + timedelta(days=183):
                raise HTTPException(status_code=400, detail="Expiry must be within 6 months and in the future")
            group.expires_at = body.expires_at
        session.commit()
        session.refresh(group)
        return group  # type: ignore[return-value]


# Instances
@router.post("/instances", response_model=schemas.InstanceOut)
async def add_instance(instance_in: schemas.InstanceCreate, current_user: User = Depends(get_current_user)) -> schemas.InstanceOut:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, instance_in.sync_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        # Ensure user is a member
        is_member = session.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).count() > 0
        if not is_member:
            raise HTTPException(status_code=403, detail="Join group before adding instance")
        # Ensure user's Immich settings exist
        user = session.get(User, current_user.id)
        if not user or not user.base_url or not user.api_key:
            raise HTTPException(status_code=400, detail="Set Immich settings first")
        # Validate album id using user's credentials
        client = ImmichClient(user.base_url, user.api_key)
        try:
            info = await client.get_album_info(instance_in.album_id)
            if not info.get("id"):
                raise HTTPException(status_code=400, detail="Album not found")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid album id")
        inst = session.query(Instance).filter(Instance.sync_id == instance_in.sync_id, Instance.user_id == current_user.id).one_or_none()
        auto_label = f"{current_user.username} ({user.base_url})"
        if inst:
            inst.album_id = instance_in.album_id
            inst.label = auto_label
            inst.size_limit_bytes = instance_in.size_limit_bytes
            inst.active = instance_in.active
            session.commit()
            session.refresh(inst)
        else:
            inst = Instance(
                user_id=current_user.id,
                sync_id=instance_in.sync_id,
                label=auto_label,
                album_id=instance_in.album_id,
                size_limit_bytes=instance_in.size_limit_bytes,
                active=instance_in.active,
            )
            session.add(inst)
            session.commit()
            session.refresh(inst)
        # return enriched InstanceOut
        return schemas.InstanceOut(
            id=inst.id,
            user_id=inst.user_id,
            sync_id=inst.sync_id,
            album_id=inst.album_id,
            size_limit_bytes=inst.size_limit_bytes,
            active=inst.active,
            username=current_user.username,
            base_url=user.base_url,
        )


@router.get("/instances", response_model=List[schemas.InstanceOut])
def list_instances(current_user: User = Depends(get_current_user)) -> List[schemas.InstanceOut]:  # noqa: B008
    with get_session() as session:
        rows = (
            session.query(Instance, User)
            .join(User, User.id == Instance.user_id)
            .filter(Instance.user_id == current_user.id)
            .all()
        )
        return [
            schemas.InstanceOut(
                id=i.id,
                user_id=i.user_id,
                sync_id=i.sync_id,
                album_id=i.album_id,
                size_limit_bytes=i.size_limit_bytes,
                active=i.active,
                username=u.username,
                base_url=u.base_url,
            )
            for (i, u) in rows
        ]


# Sync
@router.post("/groups/{group_id}/sync")
def trigger_sync(group_id: int, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:  # noqa: B008
    # Ownership or membership check
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        is_member = session.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).count() > 0
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")
    sync_service.run_sync_group_in_thread(group_id)
    return {"status": "started"}


@router.get("/groups/{group_id}/progress", response_model=schemas.SyncProgress)
def get_progress(group_id: int, current_user: User = Depends(get_current_user)) -> schemas.SyncProgress:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        is_member = session.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).count() > 0
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")
    progress = sync_service.get_progress(group_id)
    return progress  # type: ignore[return-value]


@router.get("/groups/{group_id}/instance_stats", response_model=List[schemas.InstanceStats])
async def get_instance_stats(group_id: int, current_user: User = Depends(get_current_user)) -> List[schemas.InstanceStats]:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        is_member = (
            session.query(GroupMember)
            .filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id)
            .count() > 0
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")
        rows = (
            session.query(Instance, User)
            .join(User, User.id == Instance.user_id)
            .filter(Instance.sync_id == group.id)
            .all()
        )

    async def _fetch(i: Instance, u: User) -> schemas.InstanceStats:
        title: str | None = None
        asset_count = 0
        if u.base_url and u.api_key:
            client = ImmichClient(u.base_url, u.api_key)
            try:
                info = await client.get_album_info(i.album_id)
                assets = info.get("assets") or []
                asset_count = len(assets)
                title = info.get("albumName") or info.get("name") or info.get("title")
            finally:
                try:
                    await client.aclose()
                except Exception:
                    pass
        return schemas.InstanceStats(instance_id=i.id, album_id=i.album_id, album_title=title, asset_count=asset_count)

    stats = await asyncio.gather(*(_fetch(i, u) for (i, u) in rows))
    return list(stats)

