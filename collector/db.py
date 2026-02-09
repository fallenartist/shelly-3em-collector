from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


async def downsample_power_readings(pool: AsyncConnectionPool, older_than_hours: int) -> int:
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
            date_trunc('minute', ts) AS ts_minute,
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
            await cur.execute(query, {"hours": older_than_hours})
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


async def get_database_size_bytes(pool: AsyncConnectionPool) -> int | None:
    query = "SELECT pg_database_size(current_database())"
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            row = await cur.fetchone()
            if row is None:
                return None
            return int(row[0])


async def prune_power_readings_by_size(
    pool: AsyncConnectionPool,
    max_bytes: int,
    batch_size: int,
    max_iterations: int,
) -> int:
    total_deleted = 0
    for _ in range(max_iterations):
        size = await get_database_size_bytes(pool)
        if size is None or size <= max_bytes:
            break
        query = """
            DELETE FROM power_readings
            WHERE id IN (
                SELECT id
                FROM power_readings
                ORDER BY ts ASC
                LIMIT %(limit)s
            )
        """
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, {"limit": batch_size})
                deleted = cur.rowcount or 0
                total_deleted += deleted
        if deleted == 0:
            break
    return total_deleted


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
