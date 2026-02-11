from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from collector.config import Settings
from collector.db import create_pool


def _parse_dt(value: str) -> datetime:
    value = value.strip().replace(" ", "T")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild power_readings_1m from raw power_readings.")
    parser.add_argument("--start", required=True, help="Start timestamp (UTC), e.g. 2026-02-09T00:00:00Z")
    parser.add_argument("--end", required=True, help="End timestamp (UTC), e.g. 2026-02-12T00:00:00Z")
    parser.add_argument(
        "--bucket-minutes",
        type=int,
        default=None,
        help="Bucket size in minutes (defaults to RETENTION_LOW_RES_MINUTES)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = Settings()

    start_ts = _parse_dt(args.start)
    end_ts = _parse_dt(args.end)
    if start_ts > end_ts:
        raise SystemExit("start must be <= end")

    bucket_minutes = args.bucket_minutes or settings.RETENTION_LOW_RES_MINUTES
    bucket_seconds = max(60, int(bucket_minutes) * 60)

    pool = create_pool(settings.DATABASE_URL)
    await pool.open()
    try:
        query = """
            INSERT INTO power_readings_1m (
                ts_minute,
                device_id,
                avg_total_power_w,
                avg_phase_a_power_w,
                avg_phase_b_power_w,
                avg_phase_c_power_w,
                avg_phase_a_voltage_v,
                avg_phase_b_voltage_v,
                avg_phase_c_voltage_v,
                avg_phase_a_current_a,
                avg_phase_b_current_a,
                avg_phase_c_current_a,
                samples
            )
            SELECT
                (timestamptz 'epoch'
                 + floor(extract(epoch from ts) / %(bucket_seconds)s)
                 * %(bucket_seconds)s * interval '1 second') AS ts_minute,
                COALESCE(device_id, 'unknown') AS device_id,
                avg(total_power_w),
                avg(phase_a_power_w),
                avg(phase_b_power_w),
                avg(phase_c_power_w),
                avg(phase_a_voltage_v),
                avg(phase_b_voltage_v),
                avg(phase_c_voltage_v),
                avg(phase_a_current_a),
                avg(phase_b_current_a),
                avg(phase_c_current_a),
                count(*) AS samples
            FROM power_readings
            WHERE ts >= %(start_ts)s AND ts < %(end_ts)s
            GROUP BY 1, 2
            ON CONFLICT (device_id, ts_minute) DO UPDATE SET
                avg_total_power_w = EXCLUDED.avg_total_power_w,
                avg_phase_a_power_w = EXCLUDED.avg_phase_a_power_w,
                avg_phase_b_power_w = EXCLUDED.avg_phase_b_power_w,
                avg_phase_c_power_w = EXCLUDED.avg_phase_c_power_w,
                avg_phase_a_voltage_v = EXCLUDED.avg_phase_a_voltage_v,
                avg_phase_b_voltage_v = EXCLUDED.avg_phase_b_voltage_v,
                avg_phase_c_voltage_v = EXCLUDED.avg_phase_c_voltage_v,
                avg_phase_a_current_a = EXCLUDED.avg_phase_a_current_a,
                avg_phase_b_current_a = EXCLUDED.avg_phase_b_current_a,
                avg_phase_c_current_a = EXCLUDED.avg_phase_c_current_a,
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
                print(f"Rebuilt 1m rows: {cur.rowcount or 0}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
