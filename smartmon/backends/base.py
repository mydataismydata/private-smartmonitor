"""The backend contract shared by every driver.

A backend knows how to READ a device (produce a DeviceState) and APPLY a command
to it. Everything above this line (poller, api, server, web) speaks DeviceState and
plain command dicts, so adding a new ecosystem later (TP-Link/Kasa, Hue, Zigbee via
MQTT, ...) is just another Backend subclass — nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DeviceState:
    """A device's live state. Fields a device doesn't have stay None and the UI
    simply doesn't render a control for them."""

    online: bool = False
    power: Optional[bool] = None
    brightness: Optional[int] = None      # 0-100
    color_temp: Optional[int] = None      # 0-100 (warm -> cool)
    mode: Optional[str] = None            # canonical AC_MODES value
    fan_speed: Optional[str] = None       # device-native fan-speed enum (raw passthrough)
    setpoint_c: Optional[float] = None    # target temperature, deg C
    current_temp_c: Optional[float] = None  # measured temperature, deg C
    power_w: Optional[float] = None       # instantaneous draw, watts (plugs)
    # Solar mini-split metering (solar_ac): PV vs. grid power + their % split.
    solar_power_w: Optional[float] = None
    grid_power_w: Optional[float] = None
    solar_percent: Optional[int] = None
    grid_percent: Optional[int] = None
    raw: Dict[str, object] = field(default_factory=dict)  # backend-native signals, for debugging

    def to_dict(self) -> Dict[str, object]:
        return {
            "online": self.online,
            "power": self.power,
            "brightness": self.brightness,
            "color_temp": self.color_temp,
            "mode": self.mode,
            "fan_speed": self.fan_speed,
            "setpoint_c": self.setpoint_c,
            "current_temp_c": self.current_temp_c,
            "power_w": self.power_w,
            "solar_power_w": self.solar_power_w,
            "grid_power_w": self.grid_power_w,
            "solar_percent": self.solar_percent,
            "grid_percent": self.grid_percent,
        }


# A command is a partial desired-state dict, e.g. {"power": True}, {"brightness": 60},
# {"mode": "cool", "setpoint": 21}. Backends apply only the keys they understand.
Command = Dict[str, object]


class Backend:
    """Interface every device driver implements. Async because the real transports
    (a TCP socket to a Tuya device, etc.) must not block the event loop."""

    async def read(self, device) -> Optional[DeviceState]:
        """Return the device's current state, or None if it couldn't be reached."""
        raise NotImplementedError

    async def apply(self, device, command: Command) -> Dict[str, object]:
        """Apply a command. Returns {"ok": bool, ...}; extra keys are backend-specific
        (e.g. {"cooldown": True, "retry_after": 240} when a change is rate-limited)."""
        raise NotImplementedError
