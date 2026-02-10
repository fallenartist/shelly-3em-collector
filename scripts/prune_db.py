from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from collector.config import Settings
except ModuleNotFoundError as exc:
    missing = exc.name or "dependency"
    if missing.startswith("pydantic"):
        print("Missing dependencies. Install with:")
        print("  python3 -m pip install -r requirements.txt")
        raise SystemExit(1) from exc
    raise
from collector.db import (
    create_pool,
    delete_energy_intervals_older_than,
    delete_energy_intervals_1h_older_than,
    delete_power_readings_1m_older_than,
    delete_power_readings_older_than,
    downsample_power_readings,
    downsample_energy_intervals,
    get_database_size_bytes,
    prune_power_storage_by_size,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prune/resize DB using current .env retention settings.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply changes without confirmation prompt.",
    )
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    settings = Settings()

    print("WARNING: This operation is irreversible.")
    print("If you increased resolution/retention recently, deleted data cannot be restored.")
    print("Settings used:")
    print(f"- RETENTION_DOWNSAMPLE_AFTER_HOURS={settings.RETENTION_DOWNSAMPLE_AFTER_HOURS}")
    print(f"- RETENTION_LOW_RES_MINUTES={settings.RETENTION_LOW_RES_MINUTES}")
    print(f"- RETENTION_LOW_RES_MAX_DAYS={settings.RETENTION_LOW_RES_MAX_DAYS}")
    print(f"- RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS={settings.RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS}")
    print(f"- RETENTION_INTERVAL_LOW_RES_HOURS={settings.RETENTION_INTERVAL_LOW_RES_HOURS}")
    print(f"- RETENTION_INTERVAL_LOW_RES_MAX_DAYS={settings.RETENTION_INTERVAL_LOW_RES_MAX_DAYS}")
    print(f"- RETENTION_MAX_DB_MB={settings.RETENTION_MAX_DB_MB}")
    print(f"- RETENTION_PRUNE_INCLUDE_INTERVALS={settings.RETENTION_PRUNE_INCLUDE_INTERVALS}")

    if not args.yes:
        try:
            response = input("Proceed with pruning? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("Aborted.")
            return
        if response not in ("y", "yes"):
            print("Aborted.")
            return

    pool = create_pool(settings.DATABASE_URL)
    await pool.open()

    if settings.RETENTION_DOWNSAMPLE_AFTER_HOURS and settings.RETENTION_DOWNSAMPLE_AFTER_HOURS > 0:
        inserted = await downsample_power_readings(
            pool,
            settings.RETENTION_DOWNSAMPLE_AFTER_HOURS,
            settings.RETENTION_LOW_RES_MINUTES * 60,
        )
        deleted = await delete_power_readings_older_than(pool, settings.RETENTION_DOWNSAMPLE_AFTER_HOURS)
        print(f"Downsampled rows inserted: {inserted}")
        print(f"Raw rows deleted: {deleted}")

    if settings.RETENTION_LOW_RES_MAX_DAYS and settings.RETENTION_LOW_RES_MAX_DAYS > 0:
        low_deleted = await delete_power_readings_1m_older_than(pool, settings.RETENTION_LOW_RES_MAX_DAYS)
        print(f"Low-res rows deleted: {low_deleted}")

    if settings.RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS and settings.RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS > 0:
        interval_inserted = await downsample_energy_intervals(
            pool,
            settings.RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS,
            settings.RETENTION_INTERVAL_LOW_RES_HOURS * 3600,
        )
        interval_deleted = await delete_energy_intervals_older_than(pool, settings.RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS)
        print(f"Interval rows inserted (low-res): {interval_inserted}")
        print(f"Interval rows deleted (raw): {interval_deleted}")

    if settings.RETENTION_INTERVAL_LOW_RES_MAX_DAYS and settings.RETENTION_INTERVAL_LOW_RES_MAX_DAYS > 0:
        interval_low_deleted = await delete_energy_intervals_1h_older_than(
            pool, settings.RETENTION_INTERVAL_LOW_RES_MAX_DAYS
        )
        print(f"Interval low-res rows deleted: {interval_low_deleted}")

    if settings.RETENTION_MAX_DB_MB and settings.RETENTION_MAX_DB_MB > 0:
        max_bytes = int(settings.RETENTION_MAX_DB_MB * 1024 * 1024)
        before = await get_database_size_bytes(pool)
        deleted = await prune_power_storage_by_size(
            pool,
            max_bytes=max_bytes,
            include_intervals=settings.RETENTION_PRUNE_INCLUDE_INTERVALS,
        )
        after = await get_database_size_bytes(pool)
        print(
            "Size-cap prune: "
            f"deleted_raw={deleted['raw']} "
            f"deleted_low={deleted['low']} "
            f"deleted_intervals={deleted['intervals']} "
            f"cutoff={deleted['cutoff']}"
        )
        if before is not None and after is not None:
            print(f"DB size: {before} -> {after} bytes")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
