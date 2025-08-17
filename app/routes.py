from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.background import BackgroundTasks
from typing import Optional

from .db import get_session
from .models import SyncGroup, Instance, AssetHash, AssetPresence, UserAccount, AuthUser, GroupMember
from .scheduler_utils import schedule_daily_jobs
from .immich_client import ImmichClient


router = APIRouter()

# --- Auth helpers ---
COOKIE_NAME = "immich_sync_uid"


def _hash_password(password: str) -> tuple[str, str]:
    import os
    import hashlib
    import base64

    salt = base64.b64encode(os.urandom(16)).decode()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), 100_000)
    return base64.b64encode(h).decode(), salt


def _verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    import hashlib
    import base64

    h = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(password_salt), 100_000)
    return base64.b64encode(h).decode() == password_hash


def _get_user_from_cookie(request: Request):
    uid = request.cookies.get(COOKIE_NAME)
    try:
        uid_int = int(uid) if uid else None
    except Exception:
        uid_int = None
    if not uid_int:
        return None
    with get_session() as session:
        return session.get(AuthUser, uid_int)
@router.get("/api/groups")
async def api_groups() -> JSONResponse:
    with get_session() as session:
        groups = session.query(SyncGroup).all()
        out = []
        for g in groups:
            out.append({
                "id": g.id,
                "name": g.name,
                "code": g.code,
                "schedule_time": g.schedule_time,
            })
    return JSONResponse(out)

@router.get("/api/groups/{group_id}")
async def api_group_detail(group_id: int) -> JSONResponse:
    with get_session() as session:
        g = session.get(SyncGroup, group_id)
        if not g:
            raise HTTPException(404)
        # Prefer GroupMember view (AuthUser-tied); fall back to instances if none
        members = session.query(GroupMember).filter(GroupMember.sync_id == g.id, GroupMember.active == True).all()
        instances = session.query(Instance).filter(Instance.sync_id == g.id).all() if not members else []
        return JSONResponse({
            "id": g.id,
            "name": g.name,
            "code": g.code,
            "schedule_time": g.schedule_time,
            "instances": [
                {
                    "id": i.id,
                    "label": i.label,
                    "base_url": i.base_url,
                    "album_id": i.album_id,
                    "size_limit_bytes": i.size_limit_bytes,
                }
                for i in instances
            ],
            "members": [
                {
                    "id": m.id,
                    "user_id": m.user_id,
                    "label": m.label,
                    "album_id": m.album_id,
                    "size_limit_bytes": m.size_limit_bytes,
                }
                for m in members
            ],
        })


# --- Auth API ---

@router.get("/api/auth/session")
async def api_auth_session(request: Request) -> JSONResponse:
    user = _get_user_from_cookie(request)
    if not user:
        return JSONResponse({"authenticated": False})
    return JSONResponse({"authenticated": True, "user": {"id": user.id, "username": user.username}})


@router.post("/api/auth/login")
async def api_auth_login(request: Request) -> JSONResponse:
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    with get_session() as session:
        user = session.query(AuthUser).filter(AuthUser.username == username).one_or_none()
        if not user or not _verify_password(password, user.password_hash, user.password_salt):
            raise HTTPException(401, detail="Invalid credentials")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, str(user.id), httponly=True, max_age=60 * 60 * 24 * 30)
    return resp


@router.post("/api/auth/register")
async def api_auth_register(request: Request) -> JSONResponse:
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    confirm = data.get("confirm_password") or ""
    captcha = (data.get("captcha_answer") or "").strip()
    base_url = (data.get("instance_base_url") or "").strip().rstrip("/")
    api_key = (data.get("instance_api_key") or "").strip()
    if captcha != "5":
        raise HTTPException(400, detail="Captcha failed")
    if not username or not password or not base_url or not api_key:
        raise HTTPException(400, detail="Missing fields")
    if password != confirm:
        raise HTTPException(400, detail="Passwords do not match")
    with get_session() as session:
        if session.query(AuthUser).filter(AuthUser.username == username).first():
            raise HTTPException(400, detail="Username already exists")
        ph, salt = _hash_password(password)
        user = AuthUser(username=username, password_hash=ph, password_salt=salt, instance_base_url=base_url, instance_api_key=api_key)
        session.add(user)
        session.commit()
        session.refresh(user)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, str(user.id), httponly=True, max_age=60 * 60 * 24 * 30)
    return resp


@router.post("/api/auth/logout")
async def api_auth_logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/")
async def index() -> JSONResponse:
    # Minimal JSON root for SPA health
    return JSONResponse({"ok": True})


@router.post("/groups")
async def create_group(request: Request, name: Optional[str] = Form(default=None), schedule_time: str = Form(default="02:00")):
    import secrets

    code = secrets.token_urlsafe(8)
    with get_session() as session:
        group = SyncGroup(code=code, name=name or "Sync", schedule_time=schedule_time)
        session.add(group)
        session.commit()
        session.refresh(group)
    schedule_daily_jobs(request.app)
    return RedirectResponse(url=f"/groups/{group.id}", status_code=303)


@router.post("/api/groups")
async def api_create_group(request: Request) -> JSONResponse:
    data = await request.json()
    name = (data.get("name") or "Sync").strip()
    schedule_time = (data.get("schedule_time") or "02:00").strip()
    import secrets
    code = secrets.token_urlsafe(8)
    with get_session() as session:
        group = SyncGroup(code=code, name=name or "Sync", schedule_time=schedule_time)
        session.add(group)
        session.commit()
        session.refresh(group)
        gid = group.id
    return JSONResponse({"ok": True, "id": gid})


@router.post("/api/groups/{group_id}/join")
async def api_join_group(request: Request, group_id: int) -> JSONResponse:
    user = _get_user_from_cookie(request)
    if not user:
        raise HTTPException(401)
    data = await request.json()
    label = (data.get("label") or user.username or "Member").strip()
    album_id = (data.get("album_id") or "").strip()
    limit_mb = int(data.get("size_limit_mb") or 100)
    if not album_id:
        raise HTTPException(400, detail="album_id required")
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        m = GroupMember(sync_id=group.id, user_id=user.id, label=label, album_id=album_id, size_limit_bytes=limit_mb * 1024 * 1024, active=True)
        session.add(m)
        session.commit()
        session.refresh(m)
        return JSONResponse({"ok": True, "member_id": m.id})


@router.post("/api/groups/{group_id}/leave")
async def api_leave_group(request: Request, group_id: int) -> JSONResponse:
    user = _get_user_from_cookie(request)
    if not user:
        raise HTTPException(401)
    with get_session() as session:
        m = session.query(GroupMember).filter(GroupMember.sync_id == group_id, GroupMember.user_id == user.id, GroupMember.active == True).one_or_none()
        if not m:
            raise HTTPException(404)
        m.active = False
        session.add(m)
        session.commit()
    return JSONResponse({"ok": True})


@router.post("/api/groups/{group_id}/sync")
async def api_trigger_sync(request: Request, group_id: int) -> JSONResponse:
    sync_service = getattr(request.app.state, "sync_service", None)
    if not sync_service:
        raise HTTPException(503, detail="Sync service not ready")
    sync_service.run_sync_group_in_thread(group_id)
    return JSONResponse({"ok": True})


@router.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail(request: Request, group_id: int) -> HTMLResponse:
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        instances = session.query(Instance).filter(Instance.sync_id == group.id).all()
        total_unique = session.query(AssetHash).filter(AssetHash.sync_id == group.id).count()
        stats: dict[int, dict[str, int | float]] = {}
        for inst in instances:
            present = (
                session.query(AssetPresence)
                .join(AssetHash, AssetPresence.asset_hash_id == AssetHash.id)
                .filter(
                    AssetPresence.instance_id == inst.id,
                    AssetHash.sync_id == group.id,
                    AssetPresence.in_album == True,
                )
                .count()
            )
            missing = max(total_unique - present, 0)
            coverage = (present / total_unique * 100.0) if total_unique else 0.0
            stats[inst.id] = {"present": present, "missing": missing, "coverage": round(coverage, 1)}
        # Build album links for UI navigation
        album_links: dict[int, str] = {}
        for inst in instances:
            base = inst.base_url.rstrip('/')
            if base.endswith('/api'):
                base = base[:-4]
            album_links[inst.id] = f"{base}/albums/{inst.album_id}"
        # Load users per instance
        users_map: dict[int, list[UserAccount]] = {}
        with get_session() as session2:
            for inst in instances:
                users_map[inst.id] = session2.query(UserAccount).filter(UserAccount.instance_id == inst.id).all()
    return request.app.state.templates.TemplateResponse(
        "sync_detail.html",
        {"request": request, "group": group, "instances": instances, "total_unique": total_unique, "stats": stats, "album_links": album_links, "users_map": users_map},
    )


@router.get("/groups/{group_id}/instances/{instance_id}/validate", response_class=HTMLResponse)
async def validate_instance_page(request: Request, group_id: int, instance_id: int) -> HTMLResponse:
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        if not inst or inst.sync_id != group_id:
            raise HTTPException(404)
    client = ImmichClient(inst.base_url, inst.api_key)
    result = await client.validate(album_id=inst.album_id)
    await client.aclose()
    return request.app.state.templates.TemplateResponse("validate.html", {"request": request, "instance": inst, "result": result})


@router.get("/api/groups/{group_id}/instances/{instance_id}/validate")
async def validate_instance_api(group_id: int, instance_id: int) -> JSONResponse:
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        if not inst or inst.sync_id != group_id:
            raise HTTPException(404)
    client = ImmichClient(inst.base_url, inst.api_key)
    result = await client.validate(album_id=inst.album_id)
    await client.aclose()
    return JSONResponse(result)


@router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_form(request: Request, group_id: int) -> HTMLResponse:
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
    return request.app.state.templates.TemplateResponse("edit_group.html", {"request": request, "group": group})


@router.post("/groups/{group_id}/edit")
async def edit_group(request: Request, group_id: int, name: Optional[str] = Form(default=None), schedule_time: str = Form(default="02:00")):
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        group.name = name or group.name
        group.schedule_time = schedule_time
        session.add(group)
        session.commit()
    schedule_daily_jobs(request.app)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.get("/groups/{group_id}/instances/new", response_class=HTMLResponse)
async def new_instance(request: Request, group_id: int) -> HTMLResponse:
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
    return request.app.state.templates.TemplateResponse("add_instance.html", {"request": request, "group": group})


@router.post("/groups/{group_id}/instances/{instance_id}/users")
async def create_user(group_id: int, instance_id: int, username: str = Form(default=None), api_key: str = Form(...)):
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        if not inst or inst.sync_id != group_id:
            raise HTTPException(404)
        user = UserAccount(instance_id=inst.id, username=username, api_key=api_key)
        session.add(user)
        session.commit()
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.post("/groups/{group_id}/instances/{instance_id}/users/{user_id}/delete")
async def delete_user(group_id: int, instance_id: int, user_id: int):
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        user = session.get(UserAccount, user_id)
        if not inst or inst.sync_id != group_id or not user or user.instance_id != inst.id:
            raise HTTPException(404)
        session.delete(user)
        session.commit()
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.post("/groups/{group_id}/instances")
async def create_instance(
    request: Request,
    group_id: int,
    label: str = Form(...),
    base_url: str = Form(...),
    api_key: str = Form(...),
    album_id: str = Form(...),
    size_limit_mb: int = Form(ge=1, default=100),
):
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        inst = Instance(
            sync_id=group.id,
            label=label,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            album_id=album_id,
            size_limit_bytes=size_limit_mb * 1024 * 1024,
        )
        session.add(inst)
        session.commit()
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.get("/groups/{group_id}/instances/{instance_id}/edit", response_class=HTMLResponse)
async def edit_instance_form(request: Request, group_id: int, instance_id: int) -> HTMLResponse:
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        inst = session.get(Instance, instance_id)
        if not group or not inst or inst.sync_id != group.id:
            raise HTTPException(404)
    return request.app.state.templates.TemplateResponse("edit_instance.html", {"request": request, "group": group, "instance": inst})


@router.post("/groups/{group_id}/instances/{instance_id}/edit")
async def edit_instance(
    request: Request,
    group_id: int,
    instance_id: int,
    label: str = Form(...),
    base_url: str = Form(...),
    api_key: str = Form(...),
    album_id: str = Form(...),
    size_limit_mb: int = Form(ge=1, default=100),
):
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        if not inst or inst.sync_id != group_id:
            raise HTTPException(404)
        inst.label = label
        inst.base_url = base_url.rstrip("/")
        inst.api_key = api_key
        inst.album_id = album_id
        inst.size_limit_bytes = size_limit_mb * 1024 * 1024
        session.add(inst)
        session.commit()
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.post("/groups/{group_id}/instances/{instance_id}/remove")
async def remove_instance(group_id: int, instance_id: int):
    with get_session() as session:
        inst = session.get(Instance, instance_id)
        if inst and inst.sync_id == group_id:
            session.delete(inst)
            session.commit()
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.post("/groups/{group_id}/sync")
async def trigger_sync(request: Request, group_id: int, tasks: BackgroundTasks):
    sync_service = getattr(request.app.state, "sync_service", None)
    if not sync_service:
        raise HTTPException(503, detail="Sync service not ready")
    # run sync in separate thread to avoid blocking the event loop / frontend
    sync_service.run_sync_group_in_thread(group_id)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.get("/api/groups/{group_id}/progress")
async def group_progress(request: Request, group_id: int) -> JSONResponse:
    sync_service = getattr(request.app.state, "sync_service", None)
    if not sync_service:
        return JSONResponse({"status": "idle"})
    data = sync_service.get_progress(group_id)
    # Attach instance label mapping for better UI labeling
    labels: dict[str, str] = {}
    with get_session() as session:
        # Prefer GroupMember labels if present
        members = session.query(GroupMember).filter(GroupMember.sync_id == group_id, GroupMember.active == True).all()
        if members:
            for m in members:
                labels[str(m.id)] = m.label
        else:
            for inst in session.query(Instance).filter(Instance.sync_id == group_id).all():
                labels[str(inst.id)] = inst.label
    data["instance_labels"] = labels
    return JSONResponse(data)


@router.get("/api/groups/{group_id}/stats")
async def group_stats(group_id: int) -> JSONResponse:
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        total_unique = session.query(AssetHash).filter(AssetHash.sync_id == group.id).count()
        rows = []
        for inst in session.query(Instance).filter(Instance.sync_id == group.id).all():
            present = (
                session.query(AssetPresence)
                .join(AssetHash, AssetPresence.asset_hash_id == AssetHash.id)
                .filter(
                    AssetPresence.instance_id == inst.id,
                    AssetHash.sync_id == group.id,
                    AssetPresence.in_album == True,
                )
                .count()
            )
            missing = max(total_unique - present, 0)
            coverage = (present / total_unique * 100.0) if total_unique else 0.0
            rows.append({
                "id": inst.id,
                "label": inst.label,
                "present": present,
                "missing": missing,
                "coverage": round(coverage, 1),
            })
    return JSONResponse({"total_unique": total_unique, "instances": rows})


@router.post("/groups/{group_id}/delete")
async def delete_group_route(group_id: int):
    with get_session() as session:
        group = session.get(SyncGroup, group_id)
        if not group:
            raise HTTPException(404)
        # Delete presences for this group's assets
        asset_ids = [a.id for a in session.query(AssetHash.id).filter(AssetHash.sync_id == group.id).all()]
        if asset_ids:
            session.query(AssetPresence).filter(AssetPresence.asset_hash_id.in_(asset_ids)).delete(synchronize_session=False)
        # Delete instances
        session.query(Instance).filter(Instance.sync_id == group.id).delete(synchronize_session=False)
        # Delete asset hashes
        session.query(AssetHash).filter(AssetHash.sync_id == group.id).delete(synchronize_session=False)
        # Delete the group
        session.delete(group)
        session.commit()
    return RedirectResponse(url="/", status_code=303)
