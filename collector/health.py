from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class HealthState:
    last_live_poll: datetime | None = None
    last_interval_poll: datetime | None = None
    last_retention_run: datetime | None = None
    last_error: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "last_live_poll": self.last_live_poll.isoformat() if self.last_live_poll else None,
            "last_interval_poll": self.last_interval_poll.isoformat() if self.last_interval_poll else None,
            "last_retention_run": self.last_retention_run.isoformat() if self.last_retention_run else None,
            "last_error": self.last_error,
        }
