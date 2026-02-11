from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from psycopg_pool import AsyncConnectionPool
from psycopg.types.json import Jsonb


@dataclass
class AlertState:
    active: bool
    last_triggered_ts: datetime | None
    cooldown_until_ts: datetime | None


def create_pool(database_url: str) -> AsyncConnectionPool:
    return AsyncConnectionPool(conninfo=database_url, open=False)


def _to_jsonb(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


async def upsert_device_settings(
    pool: AsyncConnectionPool,
    device_id: str,
    timezone: str | None,
    location: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> None:
    query = """
        INSERT INTO device_settings (
            device_id, timezone, location, config, last_seen_ts
        ) VALUES (
            %(device_id)s, %(timezone)s, %(location)s, %(config)s, now() AT TIME ZONE 'utc'
        )
        ON CONFLICT (device_id) DO UPDATE SET
            timezone = EXCLUDED.timezone,
            location = EXCLUDED.location,
            config = EXCLUDED.config,
            last_seen_ts = EXCLUDED.last_seen_ts
    """
    params = {
        "device_id": device_id,
        "timezone": timezone,
        "location": _to_jsonb(location),
        "config": _to_jsonb(config),
    }
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)


async def downsample_power_readings(
    pool: AsyncConnectionPool,
    older_than_hours: int,
    bucket_seconds: int,
) -> int:
    bucket_seconds = max(60, int(bucket_seconds))
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
            count(*)
        FROM power_readings
        WHERE ts < (now() AT TIME ZONE 'utc') - (%(hours)s || ' hours')::interval
        GROUP BY 1, 2
        ON CONFLICT (device_id, ts_minute) DO NOTHING
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"hours": older_than_hours, "bucket_seconds": bucket_seconds})
            return cur.rowcount or 0


async def delete_power_readings_older_than(pool: AsyncConnectionPool, older_than_hours: int) -> int:
    query = """
        DELETE FROM power_readings
        WHERE ts < (now() AT TIME ZONE 'utc') - (%(hours)s || ' hours')::interval
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"hours": older_than_hours})
            return cur.rowcount or 0


async def delete_power_readings_1m_older_than(pool: AsyncConnectionPool, older_than_days: int) -> int:
    query = """
        DELETE FROM power_readings_1m
        WHERE ts_minute < (now() AT TIME ZONE 'utc') - (%(days)s || ' days')::interval
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"days": older_than_days})
            return cur.rowcount or 0


async def downsample_energy_intervals(
    pool: AsyncConnectionPool,
    older_than_days: int,
    bucket_seconds: int,
) -> int:
    bucket_seconds = max(3600, int(bucket_seconds))
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
            sum(energy_wh) * 3600.0 / %(bucket_seconds)s AS avg_power_w,
            count(*) AS samples
        FROM energy_intervals
        WHERE start_ts < (now() AT TIME ZONE 'utc') - (%(days)s || ' days')::interval
        GROUP BY 1, 2, 3
        ON CONFLICT (device_id, channel, ts_hour) DO NOTHING
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"days": older_than_days, "bucket_seconds": bucket_seconds})
            return cur.rowcount or 0


async def upsert_energy_intervals_1h_range(
    pool: AsyncConnectionPool,
    start_ts: datetime,
    end_ts: datetime,
    bucket_seconds: int,
) -> int:
    bucket_seconds = max(3600, int(bucket_seconds))
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
            sum(energy_wh) * 3600.0 / %(bucket_seconds)s AS avg_power_w,
            count(*) AS samples
        FROM energy_intervals
        WHERE start_ts >= %(start_ts)s AND start_ts <= %(end_ts)s
        GROUP BY 1, 2, 3
        ON CONFLICT (device_id, channel, ts_hour) DO UPDATE SET
            energy_wh = EXCLUDED.energy_wh,
            avg_power_w = EXCLUDED.avg_power_w,
            samples = EXCLUDED.samples
    """
    params = {"start_ts": start_ts, "end_ts": end_ts, "bucket_seconds": bucket_seconds}
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return cur.rowcount or 0


async def get_database_size_bytes(pool: AsyncConnectionPool) -> int | None:
    query = "SELECT pg_database_size(current_database())"
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            row = await cur.fetchone()
            if row is None:
                return None
            return int(row[0])


async def prune_power_storage_by_size(
    pool: AsyncConnectionPool,
    max_bytes: int,
    include_intervals: bool = False,
) -> dict[str, int | None]:
    size = await get_database_size_bytes(pool)
    if size is None or size <= max_bytes:
        return {"raw": 0, "low": 0, "intervals": 0, "cutoff": None}

    deleted_raw = 0
    deleted_low = 0
    deleted_intervals = 0
    cutoff: datetime | None = None

    for _ in range(5):
        size = await get_database_size_bytes(pool)
        if size is None or size <= max_bytes:
            break

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        (SELECT MIN(ts) FROM power_readings) AS pr_min,
                        (SELECT MAX(ts) FROM power_readings) AS pr_max,
                        (SELECT MIN(ts_minute) FROM power_readings_1m) AS pr1_min,
                        (SELECT MAX(ts_minute) FROM power_readings_1m) AS pr1_max,
                        (SELECT MIN(start_ts) FROM energy_intervals) AS ei_min,
                        (SELECT MAX(start_ts) FROM energy_intervals) AS ei_max,
                        (SELECT MIN(ts_hour) FROM energy_intervals_1h) AS ei1_min,
                        (SELECT MAX(ts_hour) FROM energy_intervals_1h) AS ei1_max
                    """
                )
                row = await cur.fetchone()

                await cur.execute(
                    """
                    SELECT
                        pg_total_relation_size('power_readings') AS pr_size,
                        pg_total_relation_size('power_readings_1m') AS pr1_size,
                        pg_total_relation_size('energy_intervals') AS ei_size,
                        pg_total_relation_size('energy_intervals_1h') AS ei1_size
                    """
                )
                size_row = await cur.fetchone()

            if row is None or size_row is None:
                break

            pr_min, pr_max, pr1_min, pr1_max, ei_min, ei_max, ei1_min, ei1_max = row
            pr_size, pr1_size, ei_size, ei1_size = size_row

            candidates_min = [ts for ts in (pr_min, pr1_min) if ts is not None]
            candidates_max = [ts for ts in (pr_max, pr1_max) if ts is not None]
            if include_intervals:
                if ei_min is not None:
                    candidates_min.append(ei_min)
                if ei_max is not None:
                    candidates_max.append(ei_max)
                if ei1_min is not None:
                    candidates_min.append(ei1_min)
                if ei1_max is not None:
                    candidates_max.append(ei1_max)

            if not candidates_min or not candidates_max:
                break

            global_min = min(candidates_min)
            global_max = max(candidates_max)
            span_seconds = (global_max - global_min).total_seconds()
            if span_seconds <= 0:
                break

            included_size = int(pr_size) + int(pr1_size)
            if include_intervals:
                included_size += int(ei_size) + int(ei1_size)

            if included_size <= 0:
                break

            bytes_over = size - max_bytes
            bytes_per_second = included_size / span_seconds
            if bytes_per_second <= 0:
                break

            seconds_to_remove = int((bytes_over / bytes_per_second) + 1)
            cutoff = global_min + timedelta(seconds=seconds_to_remove)
            if cutoff > global_max:
                cutoff = global_max

            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM power_readings WHERE ts < %(cutoff)s",
                    {"cutoff": cutoff},
                )
                deleted_raw += cur.rowcount or 0

            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM power_readings_1m WHERE ts_minute < %(cutoff)s",
                    {"cutoff": cutoff},
                )
                deleted_low += cur.rowcount or 0

            if include_intervals:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM energy_intervals WHERE start_ts < %(cutoff)s",
                        {"cutoff": cutoff},
                    )
                    deleted_intervals += cur.rowcount or 0

                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM energy_intervals_1h WHERE ts_hour < %(cutoff)s",
                        {"cutoff": cutoff},
                    )
                    deleted_intervals += cur.rowcount or 0

        if cutoff == global_max:
            break

    return {
        "raw": deleted_raw,
        "low": deleted_low,
        "intervals": deleted_intervals,
        "cutoff": cutoff,
    }


async def delete_energy_intervals_older_than(pool: AsyncConnectionPool, older_than_days: int) -> int:
    query = """
        DELETE FROM energy_intervals
        WHERE start_ts < (now() AT TIME ZONE 'utc') - (%(days)s || ' days')::interval
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"days": older_than_days})
            return cur.rowcount or 0


async def delete_energy_intervals_1h_older_than(pool: AsyncConnectionPool, older_than_days: int) -> int:
    query = """
        DELETE FROM energy_intervals_1h
        WHERE ts_hour < (now() AT TIME ZONE 'utc') - (%(days)s || ' days')::interval
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"days": older_than_days})
            return cur.rowcount or 0


async def insert_power_reading(
    pool: AsyncConnectionPool,
    ts: datetime,
    device_id: str | None,
    total_power_w: float | None,
    phase_a_power_w: float | None,
    phase_b_power_w: float | None,
    phase_c_power_w: float | None,
    phase_a_voltage_v: float | None,
    phase_b_voltage_v: float | None,
    phase_c_voltage_v: float | None,
    phase_a_current_a: float | None,
    phase_b_current_a: float | None,
    phase_c_current_a: float | None,
) -> None:
    query = """
        INSERT INTO power_readings (
            ts, device_id, total_power_w,
            phase_a_power_w, phase_b_power_w, phase_c_power_w,
            phase_a_voltage_v, phase_b_voltage_v, phase_c_voltage_v,
            phase_a_current_a, phase_b_current_a, phase_c_current_a
        ) VALUES (
            %(ts)s, %(device_id)s, %(total_power_w)s,
            %(phase_a_power_w)s, %(phase_b_power_w)s, %(phase_c_power_w)s,
            %(phase_a_voltage_v)s, %(phase_b_voltage_v)s, %(phase_c_voltage_v)s,
            %(phase_a_current_a)s, %(phase_b_current_a)s, %(phase_c_current_a)s
        )
    """
    params = {
        "ts": ts,
        "device_id": device_id,
        "total_power_w": total_power_w,
        "phase_a_power_w": phase_a_power_w,
        "phase_b_power_w": phase_b_power_w,
        "phase_c_power_w": phase_c_power_w,
        "phase_a_voltage_v": phase_a_voltage_v,
        "phase_b_voltage_v": phase_b_voltage_v,
        "phase_c_voltage_v": phase_c_voltage_v,
        "phase_a_current_a": phase_a_current_a,
        "phase_b_current_a": phase_b_current_a,
        "phase_c_current_a": phase_c_current_a,
    }
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)


async def upsert_energy_interval(
    pool: AsyncConnectionPool,
    device_id: str | None,
    channel: int | None,
    start_ts: datetime,
    end_ts: datetime,
    energy_wh: float | None,
    avg_power_w: float | None,
    meta: dict[str, Any] | None,
) -> None:
    query = """
        INSERT INTO energy_intervals (
            device_id, channel, start_ts, end_ts, energy_wh, avg_power_w, meta
        ) VALUES (
            %(device_id)s, %(channel)s, %(start_ts)s, %(end_ts)s, %(energy_wh)s, %(avg_power_w)s, %(meta)s
        )
        ON CONFLICT (device_id, channel, start_ts, end_ts) DO NOTHING
    """
    params = {
        "device_id": device_id,
        "channel": channel,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "energy_wh": energy_wh,
        "avg_power_w": avg_power_w,
        "meta": _to_jsonb(meta),
    }
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)


async def insert_alert_event(
    pool: AsyncConnectionPool,
    ts: datetime,
    alert_type: str,
    value: float | None,
    details: dict[str, Any] | None,
) -> None:
    query = """
        INSERT INTO alert_events (ts, type, value, details)
        VALUES (%(ts)s, %(type)s, %(value)s, %(details)s)
    """
    params = {"ts": ts, "type": alert_type, "value": value, "details": _to_jsonb(details)}
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)


async def get_alert_state(pool: AsyncConnectionPool, alert_type: str) -> AlertState | None:
    query = """
        SELECT active, last_triggered_ts, cooldown_until_ts
        FROM alert_state
        WHERE type = %(type)s
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, {"type": alert_type})
            row = await cur.fetchone()
            if row is None:
                return None
            return AlertState(
                active=row[0],
                last_triggered_ts=row[1],
                cooldown_until_ts=row[2],
            )


async def upsert_alert_state(
    pool: AsyncConnectionPool,
    alert_type: str,
    active: bool,
    last_triggered_ts: datetime | None,
    cooldown_until_ts: datetime | None,
) -> None:
    query = """
        INSERT INTO alert_state (type, active, last_triggered_ts, cooldown_until_ts)
        VALUES (%(type)s, %(active)s, %(last_triggered_ts)s, %(cooldown_until_ts)s)
        ON CONFLICT (type) DO UPDATE SET
            active = EXCLUDED.active,
            last_triggered_ts = EXCLUDED.last_triggered_ts,
            cooldown_until_ts = EXCLUDED.cooldown_until_ts
    """
    params = {
        "type": alert_type,
        "active": active,
        "last_triggered_ts": last_triggered_ts,
        "cooldown_until_ts": cooldown_until_ts,
    }
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
