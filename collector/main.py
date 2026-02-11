from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web

from .alert import AlertConfig, AlertEngine
from .config import Settings
from .db import (
    create_pool,
    delete_power_readings_older_than,
    delete_power_readings_1m_older_than,
    delete_energy_intervals_older_than,
    downsample_power_readings,
    insert_alert_event,
    insert_power_reading,
    prune_power_storage_by_size,
    upsert_device_settings,
    upsert_energy_interval,
    upsert_energy_intervals_1h_range,
)
from .health import HealthState
from .ingest import extract_power_reading
from .intervals import parse_emdata_data
from .logger import log
from .shelly_rpc import ShellyRpc
from .trigger import HttpTrigger

ALERT_TYPE_HIGH_POWER = "HIGH_POWER"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DeviceContext:
    device_id: str | None = None
    timezone: str | None = None


def _device_id_from_sys_config(payload: dict[str, Any]) -> str | None:
    device = payload.get("device")
    if isinstance(device, dict):
        for key in ("mac", "id", "name"):
            val = device.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


def _timezone_from_sys_config(payload: dict[str, Any]) -> str | None:
    location = payload.get("location")
    if isinstance(location, dict):
        tz = location.get("tz")
        if isinstance(tz, str) and tz.strip():
            return tz
    return None


async def live_poll_loop(
    rpc: ShellyRpc,
    pool,
    alert_engine: AlertEngine,
    trigger: HttpTrigger,
    poll_seconds: int,
    health: HealthState,
    device_ctx: DeviceContext,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            status = await rpc.get_status()
            reading = extract_power_reading(status)
            device_ctx.device_id = reading.device_id or device_ctx.device_id
            await insert_power_reading(
                pool,
                reading.ts,
                reading.device_id,
                reading.total_power_w,
                reading.phase_a_power_w,
                reading.phase_b_power_w,
                reading.phase_c_power_w,
                reading.phase_a_voltage_v,
                reading.phase_b_voltage_v,
                reading.phase_c_voltage_v,
                reading.phase_a_current_a,
                reading.phase_b_current_a,
                reading.phase_c_current_a,
            )
            health.last_live_poll = _utcnow()
            triggered = await alert_engine.process(ALERT_TYPE_HIGH_POWER, reading.total_power_w)
            if triggered:
                log("alert.triggered", type=ALERT_TYPE_HIGH_POWER, value=reading.total_power_w)
                await insert_alert_event(
                    pool,
                    _utcnow(),
                    ALERT_TYPE_HIGH_POWER,
                    reading.total_power_w,
                    {"device_id": reading.device_id},
                )
                asyncio.create_task(trigger.pulse())
        except Exception as exc:  # noqa: BLE001
            health.last_error = str(exc)
            log("poll.error", loop="live", error=str(exc))
        await asyncio.sleep(poll_seconds)


async def interval_poll_loop(
    rpc: ShellyRpc,
    pool,
    device_ctx: DeviceContext,
    emdata_id: int,
    lookback_records: int,
    max_records_per_call: int,
    max_chunks_per_poll: int,
    interval_bucket_hours: int,
    poll_seconds: int,
    health: HealthState,
    stop: asyncio.Event,
) -> None:
    last_record_ts: datetime | None = None
    while not stop.is_set():
        try:
            records_payload = await rpc.get_emdata_records({"id": emdata_id})
            data_blocks = records_payload.get("data_blocks")
            if not isinstance(data_blocks, list) or not data_blocks:
                log("intervals.no_blocks")
                await asyncio.sleep(poll_seconds)
                continue

            candidates = [b for b in data_blocks if isinstance(b, dict) and isinstance(b.get("ts"), (int, float))]
            if not candidates:
                log("intervals.no_valid_blocks")
                await asyncio.sleep(poll_seconds)
                continue
            latest_block = max(candidates, key=lambda b: b["ts"])
            block_ts = int(latest_block["ts"])
            period = int(latest_block.get("period", 0))
            records = int(latest_block.get("records", 0))
            if period <= 0 or records <= 0:
                log("intervals.bad_block", block=latest_block)
                await asyncio.sleep(poll_seconds)
                continue

            block_start = datetime.fromtimestamp(block_ts, tz=timezone.utc)
            block_end = block_start + timedelta(seconds=period * (records - 1))

            if last_record_ts is None:
                if lookback_records > 0:
                    lookback_start = block_end - timedelta(seconds=period * (lookback_records - 1))
                    start_ts = max(block_start, lookback_start)
                else:
                    start_ts = block_start
            else:
                start_ts = max(block_start, last_record_ts + timedelta(seconds=period))

            if start_ts > block_end:
                log("intervals.up_to_date")
                await asyncio.sleep(poll_seconds)
                continue

            max_records = max(1, int(max_records_per_call))
            max_chunks = max(1, int(max_chunks_per_poll))
            bucket_seconds = max(1, int(interval_bucket_hours)) * 3600
            inserted = 0
            chunks = 0
            chunk_start = start_ts
            last_interval_ts: datetime | None = None
            while chunk_start <= block_end and chunks < max_chunks:
                chunk_end = min(block_end, chunk_start + timedelta(seconds=period * (max_records - 1)))
                data_payload = await rpc.get_emdata_data(
                    {"id": emdata_id, "ts": int(chunk_start.timestamp()), "end_ts": int(chunk_end.timestamp())}
                )
                intervals = list(parse_emdata_data(data_payload, device_ctx.device_id))
                if not intervals:
                    log("intervals.empty_chunk", start_ts=chunk_start, end_ts=chunk_end)
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
                    inserted += 1
                last_interval_ts = max(i.start_ts for i in intervals)
                hour_start = chunk_start.replace(minute=0, second=0, microsecond=0)
                hour_end = last_interval_ts.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                await upsert_energy_intervals_1h_range(pool, hour_start, hour_end, bucket_seconds)
                chunk_start = last_interval_ts + timedelta(seconds=period)
                chunks += 1
            if last_interval_ts is not None:
                last_record_ts = last_interval_ts
            health.last_interval_poll = _utcnow()
            log(
                "intervals.ingested",
                count=inserted,
                chunks=chunks,
                start_ts=start_ts,
                end_ts=last_record_ts,
            )
        except Exception as exc:  # noqa: BLE001
            health.last_error = str(exc)
            log("poll.error", loop="interval", error=str(exc))
        await asyncio.sleep(poll_seconds)


async def retention_loop(
    pool,
    run_seconds: int,
    downsample_after_hours: int | None,
    low_res_minutes: int,
    low_res_max_days: int | None,
    interval_raw_max_days: int | None,
    prune_include_intervals: bool,
    max_db_mb: int | None,
    health: HealthState,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            if downsample_after_hours and downsample_after_hours > 0:
                inserted = await downsample_power_readings(
                    pool,
                    downsample_after_hours,
                    low_res_minutes * 60,
                )
                deleted = await delete_power_readings_older_than(pool, downsample_after_hours)
                log(
                    "retention.downsample",
                    inserted=inserted,
                    deleted=deleted,
                    older_than_hours=downsample_after_hours,
                    low_res_minutes=low_res_minutes,
                )

            if low_res_max_days and low_res_max_days > 0:
                low_res_deleted = await delete_power_readings_1m_older_than(pool, low_res_max_days)
                if low_res_deleted:
                    log("retention.low_res_prune", deleted=low_res_deleted, older_than_days=low_res_max_days)

            if interval_raw_max_days and interval_raw_max_days > 0:
                interval_deleted = await delete_energy_intervals_older_than(pool, interval_raw_max_days)
                if interval_deleted:
                    log(
                        "retention.interval_raw_prune",
                        deleted=interval_deleted,
                        older_than_days=interval_raw_max_days,
                    )

            if max_db_mb and max_db_mb > 0:
                max_bytes = int(max_db_mb * 1024 * 1024)
                deleted = await prune_power_storage_by_size(
                    pool,
                    max_bytes=max_bytes,
                    include_intervals=prune_include_intervals,
                )
                if deleted["raw"] or deleted["low"] or deleted["intervals"]:
                    log(
                        "retention.prune",
                        deleted_raw=deleted["raw"],
                        deleted_low=deleted["low"],
                        deleted_intervals=deleted["intervals"],
                        include_intervals=prune_include_intervals,
                        cutoff=deleted["cutoff"],
                        max_db_mb=max_db_mb,
                    )

            health.last_retention_run = _utcnow()
        except Exception as exc:  # noqa: BLE001
            health.last_error = str(exc)
            log("retention.error", error=str(exc))
        await asyncio.sleep(run_seconds)


async def health_app(health: HealthState, trigger: HttpTrigger, settings: Settings) -> web.Application:
    app = web.Application()

    async def handle(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", **health.as_dict()})

    async def trigger_test(request: web.Request) -> web.Response:
        token = settings.TEST_TRIGGER_TOKEN
        if token:
            provided = request.query.get("token")
            if provided != token:
                return web.json_response({"status": "forbidden"}, status=403)
        asyncio.create_task(trigger.pulse())
        return web.json_response({"status": "triggered"})

    app.router.add_get("/healthz", handle)
    app.router.add_get("/trigger/test", trigger_test)
    return app


async def run() -> None:
    settings = Settings()
    health = HealthState()
    device_ctx = DeviceContext()

    pool = create_pool(settings.DATABASE_URL)
    await pool.open()

    rpc = ShellyRpc(settings.shelly_base_url, settings.SHELLY_TIMEOUT_MS)

    try:
        sys_config = await rpc.get_sys_config()
        tz = _timezone_from_sys_config(sys_config)
        device_id = _device_id_from_sys_config(sys_config) or device_ctx.device_id
        location = sys_config.get("location") if isinstance(sys_config.get("location"), dict) else None
        if device_id:
            await upsert_device_settings(pool, device_id, tz, location, sys_config)
            device_ctx.device_id = device_id
            device_ctx.timezone = tz
            log("device.config", device_id=device_id, timezone=tz)
        else:
            log("device.config.missing_id")
    except Exception as exc:  # noqa: BLE001
        log("device.config.error", error=str(exc))

    trigger = HttpTrigger(
        settings.TRIGGER_HTTP_URL,
        settings.TRIGGER_HTTP_ON_URL,
        settings.TRIGGER_HTTP_OFF_URL,
        settings.TRIGGER_HTTP_METHOD,
        settings.ALERT_TRIGGER_SECONDS,
    )

    alert_engine = AlertEngine(
        AlertConfig(
            threshold_w=settings.ALERT_POWER_W,
            sustain_seconds=settings.ALERT_SUSTAIN_SECONDS,
            cooldown_seconds=settings.ALERT_COOLDOWN_SECONDS,
        ),
        pool,
    )
    await alert_engine.load_state(ALERT_TYPE_HIGH_POWER)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (AttributeError, NotImplementedError):
            pass

    app = await health_app(health, trigger, settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.HEALTHZ_PORT)
    await site.start()

    log("service.started", port=settings.HEALTHZ_PORT)

    tasks = [
        asyncio.create_task(
            live_poll_loop(
                rpc,
                pool,
                alert_engine,
                trigger,
                settings.POLL_LIVE_SECONDS,
                health,
                device_ctx,
                stop,
            )
        ),
        asyncio.create_task(
            interval_poll_loop(
                rpc,
                pool,
                device_ctx,
                settings.EM_DATA_ID,
                settings.EMDATA_LOOKBACK_RECORDS,
                settings.EMDATA_MAX_RECORDS,
                settings.EMDATA_MAX_CHUNKS_PER_POLL,
                settings.RETENTION_INTERVAL_LOW_RES_HOURS,
                settings.POLL_INTERVAL_DATA_SECONDS,
                health,
                stop,
            )
        ),
        asyncio.create_task(
            retention_loop(
                pool,
                settings.RETENTION_RUN_SECONDS,
                settings.RETENTION_DOWNSAMPLE_AFTER_HOURS,
                settings.RETENTION_LOW_RES_MINUTES,
                settings.RETENTION_LOW_RES_MAX_DAYS,
                settings.RETENTION_INTERVAL_RAW_MAX_DAYS,
                settings.RETENTION_PRUNE_INCLUDE_INTERVALS,
                settings.RETENTION_MAX_DB_MB,
                health,
                stop,
            )
        ),
    ]

    await stop.wait()
    log("service.stopping")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await runner.cleanup()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
