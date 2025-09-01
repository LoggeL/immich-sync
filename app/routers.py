from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import schemas
from .auth import authenticate_user, create_access_token, get_current_user, get_password_hash
from .db import get_session
from .models import GroupMember, Instance, SyncGroup, User
from .sync_service import SyncService


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


# Groups
@router.post("/groups", response_model=schemas.GroupOut)
def create_group(group_in: schemas.GroupCreate, current_user: User = Depends(get_current_user)) -> schemas.GroupOut:  # noqa: B008
    with get_session() as session:
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
        inst = session.query(Instance).filter(Instance.sync_id == group.id).all()
        out = schemas.GroupDetailOut.model_validate(group)
        out.instances = [schemas.InstanceOut.model_validate(i) for i in inst]
        return out


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


# Instances
@router.post("/instances", response_model=schemas.InstanceOut)
def add_instance(instance_in: schemas.InstanceCreate, current_user: User = Depends(get_current_user)) -> schemas.InstanceOut:  # noqa: B008
    with get_session() as session:
        group = session.get(SyncGroup, instance_in.sync_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        # Ensure user is a member
        is_member = session.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).count() > 0
        if not is_member:
            raise HTTPException(status_code=403, detail="Join group before adding instance")
        inst = Instance(
            user_id=current_user.id,
            sync_id=instance_in.sync_id,
            label=instance_in.label,
            base_url=instance_in.base_url,
            api_key=instance_in.api_key,
            album_id=instance_in.album_id,
            size_limit_bytes=instance_in.size_limit_bytes,
            active=instance_in.active,
        )
        session.add(inst)
        session.commit()
        session.refresh(inst)
        return inst  # type: ignore[return-value]


@router.get("/instances", response_model=List[schemas.InstanceOut])
def list_instances(current_user: User = Depends(get_current_user)) -> List[schemas.InstanceOut]:  # noqa: B008
    with get_session() as session:
        inst = session.query(Instance).filter(Instance.user_id == current_user.id).all()
        return inst  # type: ignore[return-value]


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

