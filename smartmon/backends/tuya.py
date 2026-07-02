"""Tuya-local (LAN) backend — generalized from SolarPi's read-only mini-split
client (appliance_client.py) into a read/write driver for plugs, lights, switches,
and A/C units.

Same core moves as SolarPi: `tinytuya` is imported lazily (so the app runs without
it until a real Tuya device is configured), blocking socket calls are pushed off the
event loop with run_in_executor, and one asyncio.Lock per device serializes the poll
read against control writes on that device's single socket.

The codec (dp_for / decode / encode) is pure and lives up top so it unit-tests on a
bare Python — no tinytuya, no network. Tuya DP numbers vary by firmware; the DEFAULT_DP
map covers the common cases and any device can override per-signal via its `dps` block
and scaling via its `options` block in smartmon.json.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

from ..devices import Device
from .base import Backend, Command, DeviceState

# Default DP (datapoint) numbers per device type. Keys are our internal signal names.
#   plug/switch DP 1 = switch; DP 19 = cur_power (deci-watts on most metering plugs)
#   light       DP 20 = switch_led, 22 = bright_value_v2, 23 = temp_value_v2 (Tuya v2 range 10..1000)
#   ac          DP 1 = switch, 4 = mode, 2 = temp_set, 3 = temp_current  (matches the EG4/Deye unit)
DEFAULT_DP: Dict[str, Dict[str, str]] = {
    "plug": {"power": "1", "power_w": "19"},
    "switch": {"power": "1"},
    "light": {"power": "20", "brightness": "22", "color_temp": "23"},
    "ac": {"power": "1", "mode": "4", "setpoint": "2", "current_temp": "3", "fan_speed": "23"},
    # EG4/Deye "Solar Aircon" mini-split: A/C DPs + the LAN-only PV/grid metering block
    # (106 solar W, 111 grid/AC W, 108 solar %, 109 grid %). Matches SolarPi's appliance.py.
    "solar_ac": {
        "power": "1", "mode": "4", "setpoint": "2", "current_temp": "3", "fan_speed": "23",
        "solar_power": "106", "grid_power": "111", "solar_percent": "108", "grid_percent": "109",
    },
}

# Per-type default mode enum mapping (canonical -> device-native). The solar mini-split reports
# cold/hot/wet/wind rather than cool/heat/dry/fan; a device can still override via options.mode_map.
DEFAULT_MODE_MAP: Dict[str, Dict[str, str]] = {
    "solar_ac": {"cool": "cold", "heat": "hot", "dry": "wet", "fan": "wind"},
}

BRIGHT_SCALE_DEFAULT = 1000  # Tuya v2 lights use 10..1000; older lights use 255 (set options.bright_scale)
BRIGHT_MIN = 10              # never send 0 as a brightness — that's what power=off is for
POWER_DIVISOR_DEFAULT = 10  # DP 19 cur_power is usually tenths of a watt
TEMP_DIVISOR_DEFAULT = 1    # most A/C firmware reports whole degrees


# ---- pure codec ---------------------------------------------------------------

def dp_for(device: Device, signal: str) -> Optional[str]:
    """Resolve a signal name (power / brightness / setpoint / ...) to this device's
    DP number: an explicit override in the device's `dps` wins, else the type default."""
    return device.dps.get(signal) or DEFAULT_DP.get(device.type, {}).get(signal)


def _num(v: object) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _as_bool(v: object) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ("true", "on", "1"):
        return True
    if s in ("false", "off", "0"):
        return False
    return None


def _int(v: object) -> Optional[int]:
    n = _num(v)
    return int(round(n)) if n is not None else None


def _as_str(v: object) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _bright_scale(device: Device) -> float:
    return float(device.option("bright_scale", BRIGHT_SCALE_DEFAULT))


def _power_divisor(device: Device) -> float:
    return float(device.option("power_divisor", POWER_DIVISOR_DEFAULT))


def _temp_divisor(device: Device) -> float:
    return float(device.option("temp_divisor", TEMP_DIVISOR_DEFAULT))


def _pct_from_scale(v: object, scale: float) -> Optional[int]:
    """Tuya 0..scale value -> 0..100 percent."""
    n = _num(v)
    if n is None or scale <= 0:
        return None
    return max(0, min(100, round(n / scale * 100)))


def _pct_to_scale(percent: object, scale: float) -> int:
    """0..100 percent -> Tuya level, clamped to [BRIGHT_MIN, scale]."""
    p = _num(percent) or 0
    raw = round(max(0.0, min(100.0, p)) / 100.0 * scale)
    return int(max(BRIGHT_MIN, min(scale, raw)))


def _from_divisor(v: object, divisor: float) -> Optional[float]:
    n = _num(v)
    if n is None:
        return None
    return round(n / divisor, 1) if divisor and divisor != 1 else n


def _mode_map(device: Device) -> Dict[str, str]:
    # Start from the type's default enum mapping, then let a per-device override win.
    m = dict(DEFAULT_MODE_MAP.get(device.type, {}))
    m.update({str(k): str(v) for k, v in (device.option("mode_map", {}) or {}).items()})
    return m


def _to_device_mode(device: Device, canonical: str) -> str:
    """canonical mode -> device-native string (identity unless mode_map overrides)."""
    return _mode_map(device).get(canonical, canonical)


def _to_canonical_mode(device: Device, native: Optional[str]) -> Optional[str]:
    """device-native mode string -> canonical (inverse of mode_map)."""
    if native is None:
        return None
    inverse = {v: k for k, v in _mode_map(device).items()}
    return inverse.get(native, native)


def decode(device: Device, dps: Dict[str, object]) -> DeviceState:
    """Map a Tuya `dps` dict onto a DeviceState, honoring the device's capabilities.
    Missing/None DPs stay None so the UI just omits that control."""
    st = DeviceState(online=True, raw=dict(dps))

    def sig(name: str):
        dp = dp_for(device, name)
        return dps.get(dp) if dp is not None else None

    st.power = _as_bool(sig("power"))
    if device.has("brightness"):
        st.brightness = _pct_from_scale(sig("brightness"), _bright_scale(device))
    if device.has("color_temp"):
        st.color_temp = _pct_from_scale(sig("color_temp"), _bright_scale(device))
    if device.has("energy"):
        st.power_w = _from_divisor(sig("power_w"), _power_divisor(device))
    if device.has("setpoint"):
        st.setpoint_c = _from_divisor(sig("setpoint"), _temp_divisor(device))
    if device.has("temperature"):
        st.current_temp_c = _from_divisor(sig("current_temp"), _temp_divisor(device))
    if device.has("mode"):
        st.mode = _to_canonical_mode(device, _as_str(sig("mode")))
    if device.has("fan"):
        st.fan_speed = _as_str(sig("fan_speed"))  # raw device enum, no mapping
    if device.has("solar_power"):
        st.solar_power_w = _num(sig("solar_power"))
        st.solar_percent = _int(sig("solar_percent"))
    if device.has("grid_power"):
        st.grid_power_w = _num(sig("grid_power"))
        st.grid_percent = _int(sig("grid_percent"))
    return st


def encode(device: Device, command: Command) -> List[Tuple[str, object]]:
    """Turn a command dict into a list of (dp, value) writes, dropping anything the
    device can't do or has no DP for."""
    out: List[Tuple[str, object]] = []
    for key, value in command.items():
        if key == "power":
            dp = dp_for(device, "power")
            if dp:
                out.append((dp, bool(value)))
        elif key == "brightness" and device.has("brightness"):
            dp = dp_for(device, "brightness")
            if dp:
                out.append((dp, _pct_to_scale(value, _bright_scale(device))))
        elif key == "color_temp" and device.has("color_temp"):
            dp = dp_for(device, "color_temp")
            if dp:
                out.append((dp, _pct_to_scale(value, _bright_scale(device))))
        elif key == "setpoint" and device.has("setpoint"):
            dp = dp_for(device, "setpoint")
            n = _num(value)
            if dp and n is not None:
                out.append((dp, int(round(n * _temp_divisor(device)))))
        elif key == "mode" and device.has("mode"):
            dp = dp_for(device, "mode")
            if dp and value is not None:
                out.append((dp, _to_device_mode(device, str(value))))
        elif key == "fan" and device.has("fan"):
            dp = dp_for(device, "fan_speed")
            if dp and value is not None:
                out.append((dp, str(value)))  # raw enum passthrough
    return out


# ---- network driver -----------------------------------------------------------

class TuyaBackend(Backend):
    """Drives real Tuya v3.x devices over the LAN. Holds one tinytuya.Device and one
    asyncio.Lock per device id, both created lazily on first use."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._devices: Dict[str, object] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock(self, device: Device) -> asyncio.Lock:
        lk = self._locks.get(device.id)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[device.id] = lk
        return lk

    def _ensure(self, device: Device):
        dev = self._devices.get(device.id)
        if dev is None:
            import tinytuya  # lazy: only needed once a real Tuya device is configured

            dev = tinytuya.Device(device.device_id, device.ip, device.local_key, version=device.version)
            dev.set_socketTimeout(self.timeout)
            self._devices[device.id] = dev
        return dev

    def _read_sync(self, device: Device) -> Optional[Dict[str, object]]:
        try:
            data = self._ensure(device).status()
        except Exception:
            self._devices.pop(device.id, None)  # force a clean reconnect next cycle
            return None
        if not isinstance(data, dict) or data.get("Error") or not isinstance(data.get("dps"), dict):
            self._devices.pop(device.id, None)
            return None
        return data["dps"]

    def _apply_sync(self, device: Device, pairs: List[Tuple[str, object]]) -> bool:
        try:
            dev = self._ensure(device)
            for dp, value in pairs:
                res = dev.set_value(dp, value)
                if isinstance(res, dict) and res.get("Error"):
                    self._devices.pop(device.id, None)
                    return False
            return True
        except Exception:
            self._devices.pop(device.id, None)
            return False

    async def read(self, device: Device) -> Optional[DeviceState]:
        loop = asyncio.get_running_loop()
        async with self._lock(device):
            dps = await loop.run_in_executor(None, self._read_sync, device)
        if not dps:
            return None
        return decode(device, dps)

    async def apply(self, device: Device, command: Command) -> Dict[str, object]:
        pairs = encode(device, command)
        if not pairs:
            return {"ok": False, "error": "no applicable command"}
        loop = asyncio.get_running_loop()
        async with self._lock(device):
            ok = await loop.run_in_executor(None, self._apply_sync, device, pairs)
        return {"ok": ok}
