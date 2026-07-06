"""Solar-inverter backend — reads a running SolarPi instance's HTTP API.

This surfaces the whole-house inverter's live PV production, battery SOC, and load as a read-only
device. Its PV output is the independent "is there sun?" signal a solar automation should trigger
on — unlike the mini-split's own DP 106, which only reads while the unit is running (0 when off).

SolarPi (the sibling app on the same Pi, default port 8000) already owns the inverter's Modbus
link and serves it at GET /api/current; we just consume that rather than fight for the serial bus.
Read-only: apply() is rejected. The field mapping (map_current) is pure and unit-tests without a
network; only the fetch touches the socket, via run_in_executor like the other backends.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional
from urllib.request import urlopen

from ..devices import Device
from .base import Backend, Command, DeviceState

# Our signal name -> SolarPi /api/current field. Overridable per device via options.field_map,
# in case a different inverter/firmware names things differently.
DEFAULT_FIELD_MAP = {"solar_power": "pv_power", "battery": "battery_soc", "load": "load_total"}
DEFAULT_URL = "http://127.0.0.1:8000"


def _num(v: object) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _int(v: object) -> Optional[int]:
    n = _num(v)
    return int(round(n)) if n is not None else None


def _field_map(device: Device) -> Dict[str, str]:
    m = dict(DEFAULT_FIELD_MAP)
    m.update({str(k): str(v) for k, v in (device.option("field_map", {}) or {}).items()})
    return m


def map_current(device: Device, current: Dict[str, object]) -> Optional[DeviceState]:
    """Map SolarPi's /api/current dict onto a DeviceState, honoring the device's capabilities.
    Returns None if the snapshot isn't available (SolarPi answers {"available": false} until it
    has read the inverter at least once)."""
    if not isinstance(current, dict) or current.get("available") is False:
        return None
    fmap = _field_map(device)
    st = DeviceState(online=True, raw=dict(current))
    if device.has("solar_power"):
        st.solar_power_w = _num(current.get(fmap["solar_power"]))
    if device.has("battery"):
        st.battery_percent = _int(current.get(fmap["battery"]))
    if device.has("load"):
        st.load_w = _num(current.get(fmap["load"]))
    return st


def base_url(device: Device, default_url: str) -> str:
    return str(device.option("url", default_url) or default_url).rstrip("/")


class SolarPiBackend(Backend):
    """Reads a solar inverter's live metrics from SolarPi's API. One backend serves every
    `solarpi` device; each device's URL comes from options.url (else the configured default)."""

    def __init__(self, default_url: str = DEFAULT_URL, timeout: float = 5.0):
        self.default_url = default_url
        self.timeout = timeout

    def _read_sync(self, device: Device) -> Optional[Dict[str, object]]:
        url = base_url(device, self.default_url) + "/api/current"
        try:
            with urlopen(url, timeout=self.timeout) as resp:  # noqa: S310 — fixed localhost URL
                data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def read(self, device: Device) -> Optional[DeviceState]:
        loop = asyncio.get_running_loop()
        current = await loop.run_in_executor(None, self._read_sync, device)
        if current is None:
            return None
        return map_current(device, current)

    async def apply(self, device: Device, command: Command) -> Dict[str, object]:
        return {"ok": False, "error": "a solar inverter is read-only"}
