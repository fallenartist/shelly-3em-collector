from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from collector.config import Settings
from collector.db import create_pool


def _parse_dt(value: str) -> datetime:
    value = value.strip().replace(" ", "T")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild energy_intervals_1h from raw intervals.")
    parser.add_argument("--start", required=True, help="Start timestamp (UTC), e.g. 2026-02-09T00:00:00Z")
    parser.add_argument("--end", required=True, help="End timestamp (UTC), e.g. 2026-02-12T00:00:00Z")
    parser.add_argument(
        "--bucket-hours",
        type=int,
        default=None,
        help="Hourly bucket size (defaults to RETENTION_INTERVAL_LOW_RES_HOURS)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = Settings()

    start_ts = _parse_dt(args.start)
    end_ts = _parse_dt(args.end)
    if start_ts > end_ts:
        raise SystemExit("start must be <= end")

    bucket_hours = args.bucket_hours or settings.RETENTION_INTERVAL_LOW_RES_HOURS
    bucket_seconds = max(1, int(bucket_hours)) * 3600

    pool = create_pool(settings.DATABASE_URL)
    await pool.open()
    try:
        query = """
            INSERT INTO energy_intervals_1h (
                ts_hour,
                device_id,
                channel,
                energy_wh,
                avg_power_w,
                samples
            )
            SELECT
                (timestamptz 'epoch'
                 + floor(extract(epoch from start_ts) / %(bucket_seconds)s)
                 * %(bucket_seconds)s * interval '1 second') AS ts_hour,
                COALESCE(device_id, 'unknown') AS device_id,
                channel,
                sum(energy_wh) AS energy_wh,
                sum(energy_wh) AS avg_power_w,
                count(*) AS samples
            FROM energy_intervals
            WHERE start_ts >= %(start_ts)s AND start_ts < %(end_ts)s
            GROUP BY 1, 2, 3
            ON CONFLICT (device_id, channel, ts_hour) DO UPDATE SET
                energy_wh = EXCLUDED.energy_wh,
                avg_power_w = EXCLUDED.avg_power_w,
                samples = EXCLUDED.samples
        """
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "bucket_seconds": bucket_seconds,
        }
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                print(f"Rebuilt hourly rows: {cur.rowcount or 0}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
