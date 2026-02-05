from __future__ import annotations

from typing import Any

import httpx


class ShellyRpc:
    def __init__(self, base_url: str, timeout_ms: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_ms / 1000.0

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/rpc/{method}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if params is None:
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=params)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected RPC response shape")
            return data

    async def get_status(self) -> dict[str, Any]:
        return await self.call("Shelly.GetStatus")

    async def get_emdata_status(self) -> dict[str, Any]:
        return await self.call("EMData.GetStatus")

    async def get_emdata_records(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.call("EMData.GetRecords", params)

    async def get_emdata_data(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.call("EMData.GetData", params)
