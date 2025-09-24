from __future__ import annotations

import asyncio
from typing import Any, Iterable, Optional, Tuple

import httpx


class ImmichClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        base = base_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        self.base_url = base
        self.api_key = api_key
        self._client = httpx.Client(base_url=self.base_url, headers={"x-api-key": self.api_key})

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)

    async def get_album_info(self, album_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_album_info, album_id)

    def _get_album_info(self, album_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/api/albums/{album_id}")
        resp.raise_for_status()
        return resp.json()

    async def list_albums(self) -> Tuple[bool, Optional[int]]:
        return await asyncio.to_thread(self._list_albums)

    def _list_albums(self) -> Tuple[bool, Optional[int]]:
        try:
            resp = self._client.get("/api/albums")
            return (resp.status_code == 200, resp.status_code)
        except httpx.HTTPStatusError as e:
            return (False, e.response.status_code if e.response else None)
        except Exception:
            return (False, None)

    @staticmethod
    def _normalize_assets_from_info(raw_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for a in raw_assets:
            normalized.append({
                "id": a.get("id"),
                "checksum": a.get("checksum") or (a.get("exifInfo", {}).get("hash") if isinstance(a.get("exifInfo"), dict) else None) or "",
                "originalFileName": a.get("originalFileName"),
                "fileCreatedAt": a.get("fileCreatedAt"),
                "fileModifiedAt": a.get("fileModifiedAt"),
                "deviceAssetId": a.get("deviceAssetId"),
                "deviceId": a.get("deviceId"),
                "size": a.get("fileSizeInByte") or a.get("size"),
                "type": a.get("type"),
            })
        return [a for a in normalized if a.get("id")]

    async def list_album_assets(self, album_id: str) -> list[dict[str, Any]]:
        info = await self.get_album_info(album_id)
        raw = info.get("assets") or []
        return self._normalize_assets_from_info(raw)

    async def download_asset(self, asset_id: str) -> bytes:
        return await asyncio.to_thread(self._download_asset, asset_id)

    def _download_asset(self, asset_id: str) -> bytes:
        resp = self._client.get(f"/api/assets/{asset_id}/original", follow_redirects=True)
        if resp.status_code == 404:
            resp = self._client.get(f"/api/assets/download/{asset_id}", follow_redirects=True)
        if resp.status_code == 404:
            resp = self._client.get(f"/api/assets/{asset_id}/download", follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    async def upload_asset(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, str],
        checksum_b64: str | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._upload_asset, filename, content, metadata, checksum_b64)

    def _upload_asset(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, str],
        checksum_b64: str | None = None,
    ) -> dict[str, Any]:
        files = {
            "assetData": (filename, content),
            "deviceAssetId": (None, metadata.get("deviceAssetId", filename)),
            "deviceId": (None, metadata.get("deviceId", "ImmichSync")),
            "fileCreatedAt": (None, metadata.get("fileCreatedAt", "")),
            "fileModifiedAt": (None, metadata.get("fileModifiedAt", metadata.get("fileCreatedAt", ""))),
        }
        headers = {"x-api-key": self.api_key}
        if checksum_b64:
            headers["x-immich-checksum"] = checksum_b64
        resp = self._client.post("/api/assets", files=files, headers=headers)
        if resp.status_code == 404:
            resp = self._client.post("/api/assets/upload", files=files, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def add_assets_to_album(self, album_id: str, asset_ids: Iterable[str]) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._add_assets_to_album, album_id, asset_ids)

    def _add_assets_to_album(self, album_id: str, asset_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = list(asset_ids)
        resp = self._client.put(f"/api/albums/{album_id}/assets", json={"ids": ids})
        if resp.status_code in (404, 405):
            resp = self._client.post(f"/api/albums/{album_id}/assets", json={"ids": ids})
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return []

    async def check_bulk_upload(self, assets: list[dict[str, str]]) -> dict[str, Any]:
        return await asyncio.to_thread(self._check_bulk_upload, assets)

    def _check_bulk_upload(self, assets: list[dict[str, str]]) -> dict[str, Any]:
        endpoints = ("/api/assets/check", "/api/asset/check")
        last_response: httpx.Response | None = None
        last_exception: httpx.HTTPError | None = None

        for endpoint in endpoints:
            try:
                resp = self._client.post(endpoint, json={"assets": assets})
            except httpx.HTTPError as exc:
                last_exception = exc
                continue

            if resp.status_code in {404, 405}:  # pragma: no cover - compatibility fallback
                last_response = resp
                continue

            resp.raise_for_status()
            return resp.json()

        if last_response is not None:
            last_response.raise_for_status()
        if last_exception is not None:
            raise last_exception

        raise RuntimeError("Bulk upload check failed for all known endpoints")