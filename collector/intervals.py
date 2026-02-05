from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from .ingest import parse_ts


@dataclass
class EnergyInterval:
    device_id: str | None
    channel: int | None
    start_ts: datetime
    end_ts: datetime
    energy_wh: float | None
    avg_power_w: float | None
    meta: dict[str, Any] | None


def parse_emdata_data(payload: dict[str, Any], device_id: str | None) -> Iterable[EnergyInterval]:
    keys = payload.get("keys")
    data = payload.get("data")
    if not isinstance(keys, list) or not isinstance(data, list):
        return []

    intervals: list[EnergyInterval] = []
    for block in data:
        if not isinstance(block, dict):
            continue
        base_ts = parse_ts(block.get("ts"))
        period = _coerce_int(block.get("period"))
        values = block.get("values")
        if base_ts is None or period is None or not isinstance(values, list):
            continue

        for idx, row in enumerate(values):
            if not isinstance(row, list):
                continue
            record_ts = base_ts + timedelta(seconds=period * idx)
            start_ts = record_ts
            end_ts = record_ts + timedelta(seconds=period)
            mapping = {str(keys[i]): row[i] for i in range(min(len(keys), len(row)))}
            intervals.extend(_intervals_from_mapping(mapping, device_id, start_ts, end_ts, period))

    return intervals


def _intervals_from_mapping(
    mapping: dict[str, Any],
    device_id: str | None,
    start_ts: datetime,
    end_ts: datetime,
    period_seconds: int,
) -> list[EnergyInterval]:
    intervals: list[EnergyInterval] = []

    phase_keys = {
        0: ["a_total_act_energy", "a_fund_act_energy"],
        1: ["b_total_act_energy", "b_fund_act_energy"],
        2: ["c_total_act_energy", "c_fund_act_energy"],
    }
    total_candidates: list[float] = []

    for channel, keys in phase_keys.items():
        energy = _first_float(mapping, keys)
        if energy is None:
            continue
        total_candidates.append(energy)
        avg_power = energy * 3600.0 / period_seconds if period_seconds > 0 else None
        intervals.append(
            EnergyInterval(
                device_id=device_id,
                channel=channel,
                start_ts=start_ts,
                end_ts=end_ts,
                energy_wh=energy,
                avg_power_w=avg_power,
                meta=mapping,
            )
        )

    if total_candidates:
        total_energy = sum(total_candidates)
        avg_power = total_energy * 3600.0 / period_seconds if period_seconds > 0 else None
        intervals.append(
            EnergyInterval(
                device_id=device_id,
                channel=3,
                start_ts=start_ts,
                end_ts=end_ts,
                energy_wh=total_energy,
                avg_power_w=avg_power,
                meta=mapping,
            )
        )

    return intervals


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _first_float(mapping: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        val = mapping.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None
