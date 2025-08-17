from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.background import BackgroundTasks
from typing import Optional

from .db import get_session
from .models import SyncGroup, Instance, AssetHash, AssetPresence
from .scheduler_utils import schedule_daily_jobs
from .immich_client import ImmichClient


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    with get_session() as session:
        groups = session.query(SyncGroup).all()
        instance_counts: dict[int, int] = {g.id: session.query(Instance).filter(Instance.sync_id == g.id).count() for g in groups}
        # Compute coverage per group as the minimum instance coverage percentage
        coverage: dict[int, int] = {}
        for g in groups:
            total_unique = session.query(AssetHash).filter(AssetHash.sync_id == g.id).count()
            cov_percent = 0
            if total_unique > 0:
                cov_values: list[float] = []
                for inst in session.query(Instance).filter(Instance.sync_id == g.id).all():
                    present = (
                        session.query(AssetPresence)
                        .join(AssetHash, AssetPresence.asset_hash_id == AssetHash.id)
                        .filter(
                            AssetPresence.instance_id == inst.id,
                            AssetHash.sync_id == g.id,
                            AssetPresence.in_album == True,
                        )
                        .count()
                    )
                    cov_values.append((present / total_unique) * 100.0)
                if cov_values:
                    cov_percent = int(round(min(cov_values)))
            coverage[g.id] = cov_percent
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {"request": request, "groups": groups, "instance_counts": instance_counts, "coverage": coverage},
    )


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
    return request.app.state.templates.TemplateResponse(
        "sync_detail.html",
        {"request": request, "group": group, "instances": instances, "total_unique": total_unique, "stats": stats, "album_links": album_links},
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
        for inst in session.query(Instance).filter(Instance.sync_id == group_id).all():
            labels[str(inst.id)] = inst.label
    data["instance_labels"] = labels
    return JSONResponse(data)


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
