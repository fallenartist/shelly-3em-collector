from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .logger import log


class HttpTrigger:
    def __init__(
        self,
        base_url: str | None,
        on_url: str | None,
        off_url: str | None,
        method: str,
        pulse_seconds: int,
    ) -> None:
        self._method = method.upper()
        self._pulse_seconds = pulse_seconds
        self._on_url, self._off_url = self._resolve_urls(base_url, on_url, off_url)

    def enabled(self) -> bool:
        return self._on_url is not None and self._off_url is not None

    async def pulse(self) -> None:
        if not self.enabled():
            log("trigger.disabled")
            return
        await self._send(self._on_url)
        await asyncio.sleep(self._pulse_seconds)
        await self._send(self._off_url)

    async def _send(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if self._method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url)
            resp.raise_for_status()

    @staticmethod
    def _resolve_urls(
        base_url: str | None,
        on_url: str | None,
        off_url: str | None,
    ) -> tuple[str | None, str | None]:
        if on_url and off_url:
            return on_url, off_url
        if base_url is None:
            return None, None
        if "{state}" in base_url:
            return base_url.format(state="on"), base_url.format(state="off")
        base = base_url.rstrip("/")
        return f"{base}/on", f"{base}/off"
