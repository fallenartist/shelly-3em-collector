from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class PowerReading:
    ts: datetime
    device_id: str | None
    total_power_w: float | None
    phase_a_power_w: float | None
    phase_b_power_w: float | None
    phase_c_power_w: float | None
    phase_a_voltage_v: float | None
    phase_b_voltage_v: float | None
    phase_c_voltage_v: float | None
    phase_a_current_a: float | None
    phase_b_current_a: float | None
    phase_c_current_a: float | None


def _find_numeric(d: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        val = d.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _all_components(status: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for value in status.values():
        if isinstance(value, dict):
            components.append(value)
    return components


def _device_id(status: dict[str, Any]) -> str | None:
    sys = status.get("sys")
    if isinstance(sys, dict):
        device = sys.get("device")
        if isinstance(device, dict):
            for key in ("id", "mac", "name"):
                val = device.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        for key in ("id", "mac"):
            val = sys.get(key)
            if isinstance(val, str) and val.strip():
                return val
    for key in ("device_id", "id", "mac"):
        val = status.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def extract_power_reading(status: dict[str, Any]) -> PowerReading:
    total_keys = ["total_act_power", "total_power", "total_pwr", "total"]
    phase_power_keys = {
        "a": ["a_act_power", "a_power", "a_pwr"],
        "b": ["b_act_power", "b_power", "b_pwr"],
        "c": ["c_act_power", "c_power", "c_pwr"],
    }
    voltage_keys = {
        "a": ["a_voltage", "a_volt", "a_v"],
        "b": ["b_voltage", "b_volt", "b_v"],
        "c": ["c_voltage", "c_volt", "c_v"],
    }
    current_keys = {
        "a": ["a_current", "a_curr", "a_i"],
        "b": ["b_current", "b_curr", "b_i"],
        "c": ["c_current", "c_curr", "c_i"],
    }

    total_power = _find_numeric(status, total_keys)
    phase_power = {"a": None, "b": None, "c": None}
    phase_voltage = {"a": None, "b": None, "c": None}
    phase_current = {"a": None, "b": None, "c": None}

    for comp in _all_components(status):
        if total_power is None:
            total_power = _find_numeric(comp, total_keys)
        for phase in ("a", "b", "c"):
            if phase_power[phase] is None:
                phase_power[phase] = _find_numeric(comp, phase_power_keys[phase])
            if phase_voltage[phase] is None:
                phase_voltage[phase] = _find_numeric(comp, voltage_keys[phase])
            if phase_current[phase] is None:
                phase_current[phase] = _find_numeric(comp, current_keys[phase])

    return PowerReading(
        ts=datetime.now(timezone.utc),
        device_id=_device_id(status),
        total_power_w=total_power,
        phase_a_power_w=phase_power["a"],
        phase_b_power_w=phase_power["b"],
        phase_c_power_w=phase_power["c"],
        phase_a_voltage_v=phase_voltage["a"],
        phase_b_voltage_v=phase_voltage["b"],
        phase_c_voltage_v=phase_voltage["c"],
        phase_a_current_a=phase_current["a"],
        phase_b_current_a=phase_current["b"],
        phase_c_current_a=phase_current["c"],
    )


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
