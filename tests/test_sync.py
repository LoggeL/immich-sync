from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.sync as sync_mod
from app.sync import ServerConfig, SyncConfig, compute_missing, index_assets, load_config


def write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_config_valid(tmp_path: Path) -> None:
    cfg = {
        "servers": [
            {
                "name": "primary",
                "base_url": "https://primary",
                "api_key": "key1",
                "album_id": "album-a",
            },
            {
                "name": "secondary",
                "base_url": "https://secondary",
                "api_key": "key2",
                "album_id": "album-b",
            },
        ]
    }
    cfg_path = write_config(tmp_path, cfg)
    loaded = load_config(cfg_path)
    assert len(loaded.servers) == 2
    assert loaded.servers[0].name == "primary"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"servers": []}, "non-empty"),
        ({"servers": [{"name": "only", "base_url": "x", "api_key": "y", "album_id": "z"}]}, "least two"),
        ({"servers": [{"base_url": "x", "api_key": "y", "album_id": "z"}, {"name": "b", "base_url": "x", "api_key": "y", "album_id": "q"}]}, "missing"),
    ],
)
def test_load_config_rejects_invalid(tmp_path: Path, payload: dict, message: str) -> None:
    cfg_path = write_config(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        load_config(cfg_path)
    assert message in str(exc.value)


def test_index_assets_and_missing() -> None:
    assets = {
        "one": [
            {"id": "1", "checksum": "chk1", "originalFileName": "a.jpg"},
            {"id": "2", "checksum": None, "originalFileName": "b.jpg"},
        ],
        "two": [
            {"id": "3", "checksum": "chk2", "originalFileName": "c.jpg"},
        ],
    }
    index, checksumless = index_assets(assets)
    assert checksumless == {"one": 1, "two": 0}
    missing = compute_missing(index)
    assert set(missing["one"]) == {"chk2"}
    assert set(missing["two"]) == {"chk1"}


@pytest.mark.asyncio
async def test_sync_assets_copies_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    assets_by_base = {
        "https://primary": [
            {
                "id": "asset-1",
                "checksum": "chk1",
                "originalFileName": "photo.jpg",
                "deviceAssetId": "asset-1",
                "deviceId": "camera",
                "fileCreatedAt": "2024-01-01T00:00:00Z",
                "fileModifiedAt": "2024-01-01T00:00:00Z",
                "size": 123,
            }
        ],
        "https://secondary": [],
    }
    uploads: list[tuple[str, str]] = []
    album_updates: list[tuple[str, tuple[str, ...]]] = []

    class FakeClient:
        def __init__(self, base_url: str, api_key: str) -> None:
            self.base_url = base_url

        async def list_album_assets(self, album_id: str) -> list[dict]:
            return list(assets_by_base[self.base_url])

        async def download_asset(self, asset_id: str) -> bytes:
            return b"binary-data"

        async def upload_asset(self, filename: str, content: bytes, metadata: dict, checksum_b64: str | None = None) -> dict:
            uploads.append((self.base_url, filename))
            return {"id": f"{self.base_url}-uploaded"}

        async def add_assets_to_album(self, album_id: str, asset_ids: list[str]) -> list[dict]:
            album_updates.append((self.base_url, tuple(asset_ids)))
            return []

        async def check_bulk_upload(self, assets: list[dict]) -> dict:
            return {"results": []}

        async def aclose(self) -> None:  # pragma: no cover - nothing to clean up
            return None

    monkeypatch.setattr(sync_mod, "ImmichClient", FakeClient)

    config = SyncConfig(
        servers=(
            ServerConfig(name="primary", base_url="https://primary", api_key="one", album_id="album-a"),
            ServerConfig(name="secondary", base_url="https://secondary", api_key="two", album_id="album-b"),
        )
    )

    summary = await sync_mod.sync_assets(config, progress=False, workers=1)

    assert summary.copied == 1
    assert summary.linked == 0
    assert summary.per_server["secondary"].copied == 1
    assert uploads == [("https://secondary", "photo.jpg")]
    assert album_updates == [("https://secondary", ("https://secondary-uploaded",))]


@pytest.mark.asyncio
async def test_sync_assets_links_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    assets_by_base = {
        "https://primary": [
            {
                "id": "asset-1",
                "checksum": "chk1",
                "originalFileName": "photo.jpg",
                "deviceAssetId": "asset-1",
                "deviceId": "camera",
                "fileCreatedAt": "2024-01-01T00:00:00Z",
                "fileModifiedAt": "2024-01-01T00:00:00Z",
                "size": 123,
            }
        ],
        "https://secondary": [],
    }
    album_updates: list[tuple[str, tuple[str, ...]]] = []
    uploads: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, base_url: str, api_key: str) -> None:
            self.base_url = base_url

        async def list_album_assets(self, album_id: str) -> list[dict]:
            return list(assets_by_base[self.base_url])

        async def download_asset(self, asset_id: str) -> bytes:
            raise AssertionError("download should not be called when asset already exists")

        async def upload_asset(self, filename: str, content: bytes, metadata: dict, checksum_b64: str | None = None) -> dict:
            uploads.append((self.base_url, filename))
            return {"id": f"{self.base_url}-uploaded"}

        async def add_assets_to_album(self, album_id: str, asset_ids: list[str]) -> list[dict]:
            album_updates.append((self.base_url, tuple(asset_ids)))
            return []

        async def check_bulk_upload(self, assets: list[dict]) -> dict:
            if self.base_url == "https://secondary":
                return {
                    "results": [
                        {
                            "action": "reject",
                            "assetId": "existing-secondary-id",
                        }
                    ]
                }
            return {"results": []}

        async def aclose(self) -> None:  # pragma: no cover
            return None

    monkeypatch.setattr(sync_mod, "ImmichClient", FakeClient)

    config = SyncConfig(
        servers=(
            ServerConfig(name="primary", base_url="https://primary", api_key="one", album_id="album-a"),
            ServerConfig(name="secondary", base_url="https://secondary", api_key="two", album_id="album-b"),
        )
    )

    summary = await sync_mod.sync_assets(config, progress=False, workers=1)

    assert summary.copied == 0
    assert summary.linked == 1
    assert uploads == []
    assert album_updates == [("https://secondary", ("existing-secondary-id",))]