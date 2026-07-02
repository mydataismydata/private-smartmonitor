"""The device model — pure, no I/O, so it unit-tests on a bare Python.

A Device is "what it is and how to reach it"; its live *state* lives in a
DeviceState (see backends/base.py) produced by whichever backend drives it. The
type fixes the device's CAPABILITIES, which is what the dashboard renders controls
from — a `light` gets a brightness slider, a `climate` gets the thermostat dial,
a `plug` shows its wattage, and so on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Supported device kinds. Each maps to a fixed capability set below.
DEVICE_TYPES = ("plug", "switch", "light", "climate", "solar_appliance")

# What each type can do — drives both the API contract and the UI controls.
#   power        on/off
#   brightness   0-100 dimmer
#   color_temp   0-100 warm..cool (optional; lights that support it)
#   energy       live power draw in watts (read-only)
#   mode         climate operating mode (see CLIMATE_MODES)
#   setpoint     climate target temperature (writable)
#   temperature  measured room temperature (read-only)
#   solar_power  PV input power, watts (read-only) — the EG4/Deye "Solar Aircon" mini-split
#   grid_power   grid/AC input power, watts (read-only), plus the PV/grid % split
CAPABILITIES: Dict[str, Tuple[str, ...]] = {
    "plug": ("power", "energy"),
    "switch": ("power",),
    "light": ("power", "brightness", "color_temp"),
    "climate": ("power", "mode", "setpoint", "temperature"),
    # The solar mini-split is a climate unit that ALSO meters its PV vs. grid power (LAN-only DPs).
    "solar_appliance": ("power", "mode", "setpoint", "temperature", "solar_power", "grid_power"),
}

# Canonical climate modes the UI/API speak. A backend maps these onto whatever the
# hardware calls them (e.g. Tuya's cool/cold, dry/wet) via a per-device mode_map.
CLIMATE_MODES = ("auto", "cool", "heat", "dry", "fan")

# Backends a device can be driven by. "demo" is the in-memory simulator.
PROTOCOLS = ("demo", "tuya")


class DeviceConfigError(ValueError):
    """A device entry in smartmon.json is missing something required or is malformed."""


@dataclass
class Device:
    """A single controllable device. Connection secrets (device_id/local_key) stay
    here on the server and are never sent to the browser — see public_dict()."""

    id: str
    name: str
    type: str
    room: str = ""
    protocol: str = "demo"

    # Tuya-local connection details (protocol == "tuya").
    ip: str = ""
    device_id: str = ""
    local_key: str = ""
    version: float = 3.3

    # Optional per-device overrides:
    #   dps: capability/signal name -> Tuya DP number, when a device deviates from
    #        the type's default DP map (see backends/tuya.py DEFAULT_DP).
    #   options: tuning knobs, e.g. {"bright_scale": 255, "power_divisor": 1,
    #            "mode_map": {"cool": "cold", "heat": "hot", "dry": "wet"}}.
    dps: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, object] = field(default_factory=dict)

    @property
    def capabilities(self) -> Tuple[str, ...]:
        return CAPABILITIES.get(self.type, ())

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def option(self, key: str, default=None):
        return self.options.get(key, default)

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "Device":
        """Build (and validate) a Device from one smartmon.json entry."""
        if not isinstance(raw, dict):
            raise DeviceConfigError(f"device entry must be an object, got {type(raw).__name__}")
        dev_id = str(raw.get("id") or "").strip()
        if not dev_id:
            raise DeviceConfigError("device is missing an 'id'")
        dtype = str(raw.get("type") or "").strip().lower()
        if dtype not in DEVICE_TYPES:
            raise DeviceConfigError(f"device {dev_id!r} has unknown type {dtype!r} (want one of {DEVICE_TYPES})")
        protocol = str(raw.get("protocol") or "tuya").strip().lower()
        if protocol not in PROTOCOLS:
            raise DeviceConfigError(f"device {dev_id!r} has unknown protocol {protocol!r} (want one of {PROTOCOLS})")

        dev = cls(
            id=dev_id,
            name=str(raw.get("name") or dev_id).strip(),
            type=dtype,
            room=str(raw.get("room") or "").strip(),
            protocol=protocol,
            ip=str(raw.get("ip") or "").strip(),
            device_id=str(raw.get("device_id") or "").strip(),
            local_key=str(raw.get("local_key") or "").strip(),
            version=float(raw.get("version") or 3.3),
            dps={str(k): str(v) for k, v in (raw.get("dps") or {}).items()},
            options=dict(raw.get("options") or {}),
        )
        if protocol == "tuya" and not (dev.ip and dev.device_id and dev.local_key):
            raise DeviceConfigError(
                f"device {dev_id!r} (tuya) needs 'ip', 'device_id', and 'local_key' "
                "(extract the local key once with `tinytuya wizard` — see README)"
            )
        return dev

    def public_dict(self) -> Dict[str, object]:
        """The browser-safe view: identity + capabilities, but no keys or IPs."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "room": self.room or "Unassigned",
            "protocol": self.protocol,
            "capabilities": list(self.capabilities),
        }

    def to_config_dict(self) -> Dict[str, object]:
        """The full record as it belongs in smartmon.json — including the secrets. Round-trips
        with from_dict(). Used to persist edits made in the UI back to disk."""
        out: Dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "room": self.room,
            "protocol": self.protocol,
        }
        if self.protocol == "tuya":
            out["ip"] = self.ip
            out["device_id"] = self.device_id
            out["local_key"] = self.local_key
            out["version"] = self.version
        if self.dps:
            out["dps"] = dict(self.dps)
        if self.options:
            out["options"] = dict(self.options)
        return out

    def editable_dict(self) -> Dict[str, object]:
        """Config for the edit form: everything except the local key (never sent to the browser),
        plus a flag saying whether a key is on file so the form can show 'leave blank to keep'."""
        cfg = self.to_config_dict()
        cfg.pop("local_key", None)
        cfg["has_local_key"] = bool(self.local_key)
        return cfg


def rooms_of(devices: List[Device]) -> List[str]:
    """Distinct room names in first-seen order, with unassigned devices last."""
    seen: List[str] = []
    for d in devices:
        room = d.room or "Unassigned"
        if room not in seen:
            seen.append(room)
    # Keep "Unassigned" at the end if present.
    if "Unassigned" in seen:
        seen = [r for r in seen if r != "Unassigned"] + ["Unassigned"]
    return seen
