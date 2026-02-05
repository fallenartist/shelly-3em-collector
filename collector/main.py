from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiohttp import web

from .alert import AlertConfig, AlertEngine
from .config import Settings
from .db import create_pool, insert_alert_event, insert_power_reading, upsert_energy_interval
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

            data_payload = await rpc.get_emdata_data(
                {"id": emdata_id, "ts": int(start_ts.timestamp()), "end_ts": int(block_end.timestamp())}
            )
            intervals = list(parse_emdata_data(data_payload, device_ctx.device_id))
            inserted = 0
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
            if intervals:
                last_record_ts = max(i.start_ts for i in intervals)
            health.last_interval_poll = _utcnow()
            log("intervals.ingested", count=inserted)
        except Exception as exc:  # noqa: BLE001
            health.last_error = str(exc)
            log("poll.error", loop="interval", error=str(exc))
        await asyncio.sleep(poll_seconds)


async def health_app(health: HealthState) -> web.Application:
    app = web.Application()

    async def handle(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", **health.as_dict()})

    app.router.add_get("/healthz", handle)
    return app


async def run() -> None:
    settings = Settings()
    health = HealthState()
    device_ctx = DeviceContext()

    pool = create_pool(settings.DATABASE_URL)
    await pool.open()

    rpc = ShellyRpc(settings.shelly_base_url, settings.SHELLY_TIMEOUT_MS)

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

    app = await health_app(health)
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
                settings.POLL_INTERVAL_DATA_SECONDS,
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
