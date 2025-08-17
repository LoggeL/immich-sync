from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Tuple
import logging
import threading
from datetime import datetime

from .db import get_session
from .models import SyncGroup, Instance, AssetHash, AssetPresence
from .immich_client import ImmichClient


class SyncService:
    def __init__(self) -> None:
        # Progress store by group id
        self._progress: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("immich_sync.SyncService")

    def get_progress(self, group_id: int) -> Dict[str, Any]:
        with self._lock:
            return dict(self._progress.get(group_id, {"status": "idle", "total": 0, "done": 0, "per_instance": {}, "oversized": {}}))

    def run_sync_group_in_thread(self, group_id: int) -> None:
        """Spawn a new thread that runs the async group sync to avoid impacting the main event loop."""
        def _runner() -> None:
            try:
                self._logger.info("Starting sync for group_id=%s in worker thread", group_id)
                asyncio.run(self.run_sync_group(group_id))
                self._logger.info("Sync finished for group_id=%s", group_id)
            except Exception as exc:  # noqa: BLE001
                self._logger.exception("Sync crashed for group_id=%s: %s", group_id, exc)

        t = threading.Thread(target=_runner, name=f"sync-group-{group_id}", daemon=True)
        t.start()

    async def _fetch_instance_assets(self, instance: Instance) -> Tuple[List[Dict[str, Any]], ImmichClient]:
        client = ImmichClient(instance.base_url, instance.api_key)
        assets = await client.list_album_assets(instance.album_id)
        return assets, client

    async def _update_index_for_instance(self, group_id: int, instance: Instance, assets: List[Dict[str, Any]]) -> None:
        with get_session() as session:
            for a in assets:
                checksum = a.get("checksum") or ""
                if not checksum:
                    continue
                ah = session.query(AssetHash).filter(AssetHash.sync_id == group_id, AssetHash.checksum == checksum).one_or_none()
                if not ah:
                    ah = AssetHash(sync_id=group_id, checksum=checksum, original_filename=a.get("originalFileName"), size_bytes=a.get("size"))
                    session.add(ah)
                    session.commit()
                    session.refresh(ah)
                ap = session.query(AssetPresence).filter(AssetPresence.asset_hash_id == ah.id, AssetPresence.instance_id == instance.id).one_or_none()
                if not ap:
                    ap = AssetPresence(asset_hash_id=ah.id, instance_id=instance.id, remote_asset_id=a["id"], in_album=True)
                    session.add(ap)
                else:
                    ap.remote_asset_id = a["id"]
                    ap.in_album = True
                    ap.last_seen_at = datetime.utcnow()
                session.commit()

    async def _copy_asset_between_instances(self, checksum: str, source: Instance, target: Instance) -> bool:
        src_client = ImmichClient(source.base_url, source.api_key)
        tgt_client = ImmichClient(target.base_url, target.api_key)
        try:
            src_assets = await src_client.list_album_assets(source.album_id)
            src = next((a for a in src_assets if a.get("checksum") == checksum and a.get("id")), None)
            if not src:
                return False
            size = src.get("size")
            if size is not None and size > target.size_limit_bytes:
                return False

            # Check if target already has this asset by checksum
            try:
                check = await tgt_client.check_bulk_upload([{"id": "x", "checksum": checksum}])
                matches = check.get("results") or check.get("assets") or []
                existing_id = None
                for m in matches:
                    # API variants: may return {id, action}, or {id, assetId}
                    if m.get("action") == "reject" and (m.get("assetId") or m.get("id")):
                        existing_id = m.get("assetId") or m.get("id")
                        break
                if existing_id:
                    await tgt_client.add_assets_to_album(target.album_id, [existing_id])
                    with get_session() as session:
                        ah = session.query(AssetHash).filter(AssetHash.sync_id == source.sync_id, AssetHash.checksum == checksum).one_or_none()
                        if ah:
                            ap = session.query(AssetPresence).filter(AssetPresence.asset_hash_id == ah.id, AssetPresence.instance_id == target.id).one_or_none()
                            if not ap:
                                ap = AssetPresence(asset_hash_id=ah.id, instance_id=target.id, remote_asset_id=existing_id, in_album=True)
                                session.add(ap)
                            else:
                                ap.remote_asset_id = existing_id
                                ap.in_album = True
                                ap.last_seen_at = datetime.utcnow()
                            session.commit()
                    return True
            except Exception:
                # If check-bulk not available, continue with download
                pass

            # Download and upload
            try:
                resp = await src_client.download_asset(src["id"])
            except Exception:
                return False
            content = await resp.aread()
            if size is None:
                size = len(content)
                if size > target.size_limit_bytes:
                    return False
            meta = {
                "deviceAssetId": src.get("deviceAssetId") or src.get("originalFileName") or checksum,
                "deviceId": f"ImmichSync-{source.label}",
                "fileCreatedAt": src.get("fileCreatedAt") or "",
                "fileModifiedAt": src.get("fileModifiedAt") or src.get("fileCreatedAt") or "",
            }
            upload_res = await tgt_client.upload_asset(src.get("originalFileName") or f"asset_{checksum}", content, meta, checksum_b64=checksum)
            new_asset_id = upload_res.get("id") or upload_res.get("assetId")
            if new_asset_id:
                await tgt_client.add_assets_to_album(target.album_id, [new_asset_id])
            with get_session() as session:
                ah = session.query(AssetHash).filter(AssetHash.sync_id == source.sync_id, AssetHash.checksum == checksum).one_or_none()
                if not ah:
                    ah = AssetHash(sync_id=source.sync_id, checksum=checksum, original_filename=src.get("originalFileName"), size_bytes=size)
                    session.add(ah)
                    session.commit()
                    session.refresh(ah)
                ap = session.query(AssetPresence).filter(AssetPresence.asset_hash_id == ah.id, AssetPresence.instance_id == target.id).one_or_none()
                if not ap:
                    ap = AssetPresence(asset_hash_id=ah.id, instance_id=target.id, remote_asset_id=new_asset_id or "", in_album=True)
                    session.add(ap)
                else:
                    ap.remote_asset_id = new_asset_id or ap.remote_asset_id
                    ap.in_album = True
                    ap.last_seen_at = datetime.utcnow()
                session.commit()
            return True
        finally:
            await asyncio.gather(src_client.aclose(), tgt_client.aclose())

    async def run_sync_group(self, group_id: int) -> None:
        self._logger.info("Sync start group_id=%s", group_id)
        with get_session() as session:
            group = session.get(SyncGroup, group_id)
            if not group:
                self._logger.warning("Sync aborted: group_id=%s not found", group_id)
                return
            instances = session.query(Instance).filter(Instance.sync_id == group.id, Instance.active == True).all()
        self._logger.info("Found %d instances for group_id=%s", len(instances), group_id)
        results = await asyncio.gather(*(self._fetch_instance_assets(inst) for inst in instances))
        instance_assets: dict[int, List[Dict[str, Any]]] = {}
        clients: list[ImmichClient] = []
        try:
            for (assets, client), inst in zip(results, instances):
                instance_assets[inst.id] = assets
                clients.append(client)
            await asyncio.gather(*(self._update_index_for_instance(group_id, inst, instance_assets[inst.id]) for inst in instances))
            union_checksums: set[str] = set()
            for assets in instance_assets.values():
                for a in assets:
                    if a.get("checksum"):
                        union_checksums.add(a["checksum"])
            self._logger.info("Union has %d unique assets for group_id=%s", len(union_checksums), group_id)
            # Initialize progress
            per_instance: Dict[int, Dict[str, int]] = {}
            total_tasks = 0
            for target in instances:
                have = {a["checksum"] for a in instance_assets[target.id] if a.get("checksum")}
                missing_list = [c for c in union_checksums if c not in have]
                per_instance[target.id] = {"missing": len(missing_list), "done": 0}
                total_tasks += len(missing_list)
            with self._lock:
                self._progress[group_id] = {"status": "running", "total": total_tasks, "done": 0, "per_instance": per_instance, "oversized": {}}
            self._logger.info("Total copy tasks=%d for group_id=%s", total_tasks, group_id)

            # Execute copies with oversize categorization
            for target in instances:
                have = {a["checksum"] for a in instance_assets[target.id] if a.get("checksum")}
                missing = [c for c in union_checksums if c not in have]
                if not missing:
                    continue
                for checksum in missing:
                    # find a source instance that has the asset and its size/filename
                    src_inst = None
                    src_asset = None
                    for inst in instances:
                        if inst.id == target.id:
                            continue
                        cand = next((a for a in instance_assets[inst.id] if a.get("checksum") == checksum), None)
                        if cand is not None:
                            src_inst = inst
                            src_asset = cand
                            break
                    if not src_inst or not src_asset:
                        # update progress even if skipped
                        with self._lock:
                            self._progress[group_id]["done"] += 1
                            self._progress[group_id]["per_instance"][target.id]["done"] += 1
                        continue
                    size = src_asset.get("size")
                    if size is not None and size > target.size_limit_bytes:
                        with self._lock:
                            oversized = self._progress[group_id]["oversized"].setdefault(target.id, [])
                            oversized.append({
                                "checksum": checksum,
                                "filename": src_asset.get("originalFileName") or "",
                                "size": size,
                            })
                            # count as processed
                            self._progress[group_id]["done"] += 1
                            self._progress[group_id]["per_instance"][target.id]["done"] += 1
                        self._logger.info(
                            "Skip oversized for target=%s checksum=%s size=%s limit=%s",
                            target.label, checksum, size, target.size_limit_bytes,
                        )
                        continue
                    await self._copy_asset_between_instances(checksum, src_inst, target)
                    # update progress counters
                    with self._lock:
                        self._progress[group_id]["done"] += 1
                        self._progress[group_id]["per_instance"][target.id]["done"] += 1
        finally:
            await asyncio.gather(*(c.aclose() for c in clients), return_exceptions=True)
            # mark finished
            with self._lock:
                if group_id in self._progress:
                    self._progress[group_id]["status"] = "idle"
            self._logger.info("Sync done group_id=%s", group_id)
