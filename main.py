from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.sync import load_config, sync_assets


logger = logging.getLogger("immich_sync")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync assets between Immich servers")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to the JSON config file (default: config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the sync without uploading any assets",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent sync workers (default: 4)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    try:
        summary = asyncio.run(
            sync_assets(
                config,
                dry_run=args.dry_run,
                workers=max(1, args.workers),
            )
        )
    except KeyboardInterrupt:
        logger.warning("Sync interrupted by user")
        return 130

    print(summary.to_report())
    if summary.errors:
        logger.error("Sync completed with %d errors", len(summary.errors))
        return 1
    logger.info("Sync completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

