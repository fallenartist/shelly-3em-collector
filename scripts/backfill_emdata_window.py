from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta

from collector.config import Settings
from collector.db import create_pool, upsert_energy_interval, upsert_energy_intervals_1h_range
from collector.intervals import parse_emdata_data
from collector.shelly_rpc import ShellyRpc


def _parse_dt(value: str) -> datetime:
    value = value.strip().replace(" ", "T")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _device_id_from_sys_config(payload: dict) -> str | None:
    device = payload.get("device")
    if isinstance(device, dict):
        for key in ("mac", "id", "name"):
            val = device.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill EMData for a specific UTC window.")
    parser.add_argument("--start", required=True, help="Start timestamp (UTC), e.g. 2026-02-03T23:00:00Z")
    parser.add_argument("--end", required=True, help="End timestamp (UTC), e.g. 2026-02-04T08:59:00Z")
    parser.add_argument("--emdata-id", type=int, default=None, help="EMData id (default from .env)")
    parser.add_argument("--max-records", type=int, default=500, help="Max records per EMData.GetData call")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = Settings()
    emdata_id = settings.EM_DATA_ID if args.emdata_id is None else args.emdata_id

    start_ts = _parse_dt(args.start)
    end_ts = _parse_dt(args.end)
    if start_ts > end_ts:
        raise SystemExit("start must be <= end")

    rpc = ShellyRpc(settings.shelly_base_url, settings.SHELLY_TIMEOUT_MS)
    pool = create_pool(settings.DATABASE_URL)
    await pool.open()
    try:
        sys_cfg = await rpc.get_sys_config()
        device_id = _device_id_from_sys_config(sys_cfg)

        period = 60
        max_records = max(1, int(args.max_records))
        bucket_seconds = max(1, int(settings.RETENTION_INTERVAL_LOW_RES_HOURS)) * 3600

        total = 0
        chunk_start = start_ts
        while chunk_start <= end_ts:
            chunk_end = min(end_ts, chunk_start + timedelta(seconds=period * (max_records - 1)))
            payload = await rpc.get_emdata_data(
                {"id": emdata_id, "ts": int(chunk_start.timestamp()), "end_ts": int(chunk_end.timestamp())}
            )
            intervals = list(parse_emdata_data(payload, device_id))
            if not intervals:
                print(f"Empty chunk: {chunk_start.isoformat()} -> {chunk_end.isoformat()}")
                break

            for interval in intervals:
                await upsert_energy_interval(
                    pool,
                    interval.device_id,
                    interval.channel,
                    interval.start_ts,
                    interval.end_ts,
                    interval.energy_wh,
                    interval.avg_power_w,
                    interval.meta,
                )
            total += len(intervals)

            last_interval_ts = max(i.start_ts for i in intervals)
            hour_start = chunk_start.replace(minute=0, second=0, microsecond=0)
            hour_end = last_interval_ts.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            await upsert_energy_intervals_1h_range(pool, hour_start, hour_end, bucket_seconds)
            chunk_start = last_interval_ts + timedelta(seconds=period)

        print(f"Inserted intervals: {total}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
