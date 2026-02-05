from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from psycopg_pool import AsyncConnectionPool

from . import db


@dataclass
class AlertConfig:
    threshold_w: float
    sustain_seconds: int
    cooldown_seconds: int


class AlertEngine:
    def __init__(self, config: AlertConfig, pool: AsyncConnectionPool) -> None:
        self._config = config
        self._pool = pool
        self._over_threshold_since: datetime | None = None
        self._cooldown_until: datetime | None = None

    async def load_state(self, alert_type: str) -> None:
        state = await db.get_alert_state(self._pool, alert_type)
        if state:
            self._cooldown_until = state.cooldown_until_ts

    async def process(self, alert_type: str, total_power_w: float | None) -> bool:
        now = datetime.now(timezone.utc)
        if total_power_w is None:
            await db.upsert_alert_state(
                self._pool,
                alert_type,
                active=False,
                last_triggered_ts=None,
                cooldown_until_ts=self._cooldown_until,
            )
            return False

        if total_power_w >= self._config.threshold_w:
            if self._over_threshold_since is None:
                self._over_threshold_since = now
            sustained = (now - self._over_threshold_since).total_seconds() >= self._config.sustain_seconds
            cooling_down = self._cooldown_until is not None and now < self._cooldown_until
            if sustained and not cooling_down:
                self._cooldown_until = now + timedelta(seconds=self._config.cooldown_seconds)
                self._over_threshold_since = None
                await db.upsert_alert_state(
                    self._pool,
                    alert_type,
                    active=True,
                    last_triggered_ts=now,
                    cooldown_until_ts=self._cooldown_until,
                )
                return True
        else:
            self._over_threshold_since = None

        await db.upsert_alert_state(
            self._pool,
            alert_type,
            active=total_power_w >= self._config.threshold_w,
            last_triggered_ts=None,
            cooldown_until_ts=self._cooldown_until,
        )
        return False
