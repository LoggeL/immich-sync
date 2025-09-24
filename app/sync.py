from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from tqdm import tqdm

from .immich_client import ImmichClient


logger = logging.getLogger(__name__)


Asset = Dict[str, Any]


@dataclass(frozen=True)
class ServerConfig:
    name: str
    base_url: str
    api_key: str
    album_id: str
    size_limit_bytes: int | None = None


@dataclass(frozen=True)
class SyncConfig:
    servers: tuple[ServerConfig, ...]


@dataclass
class ServerStats:
    initial_assets: int
    missing_before: int
    remaining: int
    copied: int = 0
    linked: int = 0
    oversized: int = 0


@dataclass
class SyncSummary:
    total_checksums: int
    copied: int = 0
    linked: int = 0
    errors: list[str] = field(default_factory=list)
    checksumless_assets: dict[str, int] = field(default_factory=dict)
    oversized: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    per_server: dict[str, ServerStats] = field(default_factory=dict)

    def to_report(self) -> str:
        lines = [
            f"Total unique assets seen: {self.total_checksums}",
            f"Copied: {self.copied}",
            f"Linked existing assets: {self.linked}",
        ]
        if any(self.checksumless_assets.values()):
            detail = ", ".join(f"{name}={count}" for name, count in self.checksumless_assets.items() if count)
            lines.append(f"Assets skipped (no checksum): {detail}")
        if self.oversized:
            lines.append("Oversized assets skipped:")
            for name, entries in self.oversized.items():
                lines.append(f"  {name}: {len(entries)}")
        if self.errors:
            lines.append("Errors:")
            for msg in self.errors:
                lines.append(f"  - {msg}")
        lines.append("Per-server stats:")
        for name, stats in self.per_server.items():
            lines.append(
                f"  {name}: had {stats.initial_assets}, missing_before {stats.missing_before}, "
                f"remaining {stats.remaining}, copied {stats.copied}, linked {stats.linked}, oversized {stats.oversized}"
            )
        return "\n".join(lines)


class OversizeError(Exception):
    """Raised when an asset is larger than the target's size budget."""


def load_config(path: Path) -> SyncConfig:
    """Load a SyncConfig from a JSON file."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - explicit message preferred
        raise ValueError(f"Config file '{path}' does not exist") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config file '{path}' is not valid JSON: {exc}") from exc

    servers_data = raw.get("servers") if isinstance(raw, dict) else None
    if not isinstance(servers_data, list) or not servers_data:
        raise ValueError("Config JSON must contain a non-empty 'servers' array")

    servers: list[ServerConfig] = []
    seen_names: set[str] = set()
    for idx, entry in enumerate(servers_data):
        if not isinstance(entry, dict):
            raise ValueError(f"servers[{idx}] must be an object")
        missing = [field for field in ("name", "base_url", "api_key", "album_id") if field not in entry]
        if missing:
            raise ValueError(f"servers[{idx}] is missing fields: {', '.join(missing)}")

        name = str(entry["name"]).strip()
        if not name:
            raise ValueError(f"servers[{idx}].name cannot be empty")
        if name in seen_names:
            raise ValueError(f"Duplicate server name '{name}' in config")
        seen_names.add(name)

        base_url = str(entry["base_url"]).strip()
        api_key = str(entry["api_key"]).strip()
        album_id = str(entry["album_id"]).strip()

        size_limit_raw = entry.get("size_limit_bytes")
        size_limit: int | None
        if size_limit_raw is None:
            size_limit = None
        else:
            try:
                size_limit = int(size_limit_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"servers[{idx}].size_limit_bytes must be an integer") from exc
            if size_limit <= 0:
                raise ValueError("size_limit_bytes must be positive if provided")

        servers.append(
            ServerConfig(
                name=name,
                base_url=base_url,
                api_key=api_key,
                album_id=album_id,
                size_limit_bytes=size_limit,
            )
        )

    if len(servers) < 2:
        raise ValueError("Config must define at least two servers to sync")

    return SyncConfig(servers=tuple(servers))


def index_assets(assets_by_server: Dict[str, List[Asset]]) -> Tuple[Dict[str, Dict[str, Asset]], Dict[str, int]]:
    """Create a checksum->asset index per server and count checksumless assets."""

    index: dict[str, dict[str, Asset]] = {}
    checksumless_counts: dict[str, int] = {}
    for name, assets in assets_by_server.items():
        per_checksum: dict[str, Asset] = {}
        missing_checksum = 0
        for asset in assets:
            checksum = asset.get("checksum")
            if not checksum:
                missing_checksum += 1
                continue
            # Preserve the first seen asset with this checksum
            per_checksum.setdefault(checksum, asset)
        index[name] = per_checksum
        checksumless_counts[name] = missing_checksum
    return index, checksumless_counts


def compute_missing(index: Dict[str, Dict[str, Asset]]) -> Dict[str, List[str]]:
    """Return the list of checksums missing on each server."""

    if not index:
        return {}
    all_checksums: set[str] = set()
    for per_server in index.values():
        all_checksums.update(per_server.keys())
    missing: dict[str, list[str]] = {}
    for name, per_server in index.items():
        missing[name] = [checksum for checksum in all_checksums if checksum not in per_server]
    return missing


async def sync_assets(
    config: SyncConfig,
    *,
    dry_run: bool = False,
    progress: bool = True,
    workers: int = 4,
) -> SyncSummary:
    """Synchronise assets between all servers defined in the config."""

    clients: dict[str, ImmichClient] = {
        server.name: ImmichClient(server.base_url, server.api_key)
        for server in config.servers
    }

    try:
        assets: dict[str, list[Asset]] = {}
        for server in config.servers:
            logger.info("Fetching assets from %s (%s)", server.name, server.base_url)
            assets[server.name] = await clients[server.name].list_album_assets(server.album_id)

        index, checksumless_counts = index_assets(assets)
        missing = compute_missing(index)
        all_checksums: list[str] = sorted({checksum for per_server in index.values() for checksum in per_server})

        summary = SyncSummary(
            total_checksums=len(all_checksums),
            checksumless_assets=checksumless_counts,
        )

        for server in config.servers:
            per_server_missing = missing.get(server.name, [])
            summary.per_server[server.name] = ServerStats(
                initial_assets=len(index.get(server.name, {})),
                missing_before=len(per_server_missing),
                remaining=len(per_server_missing),
            )

        tasks: list[tuple[str, ServerConfig, Asset, ServerConfig]] = []
        for checksum in all_checksums:
            source_config, source_asset = _select_source(config.servers, index, checksum)
            if source_config is None or source_asset is None:
                summary.errors.append(f"No source available for checksum {checksum}")
                continue

            for target in config.servers:
                if target.name == source_config.name:
                    continue
                if checksum in index.get(target.name, {}):
                    continue
                tasks.append((checksum, source_config, source_asset, target))

        progress_bar = None
        if progress and tasks:
            progress_bar = tqdm(total=len(tasks), desc="Syncing assets", unit="asset")

        semaphore = asyncio.Semaphore(max(1, int(workers)))

        async def process_task(checksum: str, source_config: ServerConfig, source_asset: Asset, target: ServerConfig) -> None:
            try:
                async with semaphore:
                    logger.info("Syncing checksum %s from %s to %s", checksum, source_config.name, target.name)

                    if dry_run:
                        summary.copied += 1
                        _register_completion(summary, target.name, checksum, index, source_asset)
                        return

                    try:
                        already_present = await _ensure_asset_on_target(
                            checksum,
                            source_config,
                            source_asset,
                            target,
                            clients,
                        )
                    except OversizeError:
                        summary.per_server[target.name].oversized += 1
                        entry = {
                            "checksum": checksum,
                            "filename": source_asset.get("originalFileName"),
                            "size": source_asset.get("size"),
                        }
                        summary.oversized.setdefault(target.name, []).append(entry)
                        logger.warning(
                            "Skipping oversized asset %s (%s) for target %s",
                            checksum,
                            entry["filename"],
                            target.name,
                        )
                        return
                    except Exception as exc:  # noqa: BLE001
                        msg = f"Failed to copy {checksum} from {source_config.name} to {target.name}: {exc}"
                        summary.errors.append(msg)
                        logger.error(msg)
                        return

                    if already_present:
                        summary.linked += 1
                        summary.per_server[target.name].linked += 1
                    else:
                        summary.copied += 1
                        summary.per_server[target.name].copied += 1

                    _register_completion(summary, target.name, checksum, index, source_asset)
            finally:
                if progress_bar:
                    progress_bar.update(1)

        try:
            await asyncio.gather(*(process_task(*task) for task in tasks))
        finally:
            if progress_bar:
                progress_bar.close()

        return summary
    finally:
        await asyncio.gather(*(client.aclose() for client in clients.values()))


def _select_source(
    servers: Iterable[ServerConfig],
    index: Dict[str, Dict[str, Asset]],
    checksum: str,
) -> tuple[ServerConfig | None, Asset | None]:
    for server in servers:
        asset = index.get(server.name, {}).get(checksum)
        if asset:
            return server, asset
    return None, None


def _register_completion(
    summary: SyncSummary,
    target_name: str,
    checksum: str,
    index: Dict[str, Dict[str, Asset]],
    source_asset: Asset,
) -> None:
    # Mark as present so subsequent targets can pick it up without re-copying
    index.setdefault(target_name, {})[checksum] = source_asset
    stats = summary.per_server.get(target_name)
    if stats and stats.remaining > 0:
        stats.remaining = max(0, stats.remaining - 1)


async def _ensure_asset_on_target(
    checksum: str,
    source: ServerConfig,
    source_asset: Asset,
    target: ServerConfig,
    clients: Dict[str, ImmichClient],
) -> bool:
    target_client = clients[target.name]

    # Respect size limits if provided
    size_limit = target.size_limit_bytes
    size = source_asset.get("size")
    if size_limit is not None and isinstance(size, int) and size > size_limit:
        raise OversizeError()

    # Prefer re-linking existing assets
    existing_id = await _find_existing_asset(target_client, checksum)
    if existing_id:
        await target_client.add_assets_to_album(target.album_id, [existing_id])
        return True

    source_client = clients[source.name]
    content = await source_client.download_asset(source_asset["id"])

    if size_limit is not None and (not isinstance(size, int)) and len(content) > size_limit:
        raise OversizeError()

    filename = source_asset.get("originalFileName") or f"asset_{checksum}"
    metadata = {
        "deviceAssetId": source_asset.get("deviceAssetId") or f"{source.name}-{checksum}",
        "deviceId": source_asset.get("deviceId") or f"ImmichSync-{source.name}",
        "fileCreatedAt": source_asset.get("fileCreatedAt") or "",
        "fileModifiedAt": source_asset.get("fileModifiedAt") or source_asset.get("fileCreatedAt") or "",
    }
    upload_response = await target_client.upload_asset(filename, content, metadata, checksum_b64=checksum)
    new_id = upload_response.get("id") or upload_response.get("assetId")
    if not new_id:
        raise RuntimeError("Target API did not return an asset id after upload")

    await target_client.add_assets_to_album(target.album_id, [new_id])
    return False


async def _find_existing_asset(client: ImmichClient, checksum: str) -> str | None:
    try:
        check = await client.check_bulk_upload([{"id": "sync", "checksum": checksum}])
    except Exception:
        return None

    candidates = check.get("results") or check.get("assets") or []
    if not isinstance(candidates, list):
        return None

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        action = entry.get("action") or entry.get("status")
        if action not in {"reject", "duplicate"}:
            continue
        existing_id = entry.get("assetId") or entry.get("existingId") or entry.get("id")
        if existing_id:
            return str(existing_id)
    return None
