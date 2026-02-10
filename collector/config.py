from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Shelly
    SHELLY_HOST: str
    SHELLY_TIMEOUT_MS: int = 5000

    # Polling
    POLL_LIVE_SECONDS: int = 10
    POLL_INTERVAL_DATA_SECONDS: int = 300
    EM_DATA_ID: int = 0
    EMDATA_LOOKBACK_RECORDS: int = 720

    # Database
    DATABASE_URL: str

    # Alerts
    ALERT_POWER_W: float = 4500
    ALERT_SUSTAIN_SECONDS: int = 120
    ALERT_COOLDOWN_SECONDS: int = 900
    ALERT_TRIGGER_SECONDS: int = 15

    # HTTP trigger (Homebridge HTTP accessory)
    TRIGGER_HTTP_URL: str | None = None
    TRIGGER_HTTP_ON_URL: str | None = None
    TRIGGER_HTTP_OFF_URL: str | None = None
    TRIGGER_HTTP_METHOD: str = "POST"

    # Service
    HEALTHZ_PORT: int = 8080
    TEST_TRIGGER_TOKEN: str | None = None

    # Retention
    RETENTION_RUN_SECONDS: int = 3600
    RETENTION_DOWNSAMPLE_AFTER_HOURS: int | None = 24
    RETENTION_LOW_RES_MINUTES: int = 1
    RETENTION_LOW_RES_MAX_DAYS: int | None = None
    RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS: int | None = 1
    RETENTION_INTERVAL_LOW_RES_HOURS: int = 1
    RETENTION_INTERVAL_LOW_RES_MAX_DAYS: int | None = None
    RETENTION_MAX_DB_MB: int | None = None
    RETENTION_PRUNE_INCLUDE_INTERVALS: bool = False

    @property
    def shelly_base_url(self) -> str:
        return f"http://{self.SHELLY_HOST}"
