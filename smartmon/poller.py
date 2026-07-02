"""The poll loop and the control entry point.

Every `interval_s` it refreshes every device's state through its backend and caches
the result in memory (the API reads straight from this cache — there's no database in
phase 1). All control goes through `apply()`, which also enforces the one bit of
device-protection policy carried over from SolarPi: a climate unit's compressor must
not be short-cycled, so on/off toggles and heat<->cool reversals are gated by a
5-minute cooldown. Plugs, lights, and switches have no such limit.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, Optional

from .backends.base import Command, DeviceState
from .devices import Device
from .registry import Registry

POWER_COOLDOWN_S = 300         # min seconds between a climate unit's on/off changes
MODE_REVERSE_COOLDOWN_S = 300  # min seconds between heat<->cool switches (compressor reversal)
_COOLING_MODES = ("cool", "dry")  # cool + dry drive the compressor the same way; heat reverses it
# Types with a compressor to protect (the plain climate unit and the solar mini-split).
COMPRESSOR_TYPES = ("climate", "solar_appliance")


def _is_compressor_reverse(from_mode: Optional[str], to_mode: Optional[str]) -> bool:
    return (from_mode in _COOLING_MODES and to_mode == "heat") or (
        from_mode == "heat" and to_mode in _COOLING_MODES
    )


class DevicePoller:
    def __init__(self, registry: Registry, interval_s: float = 10.0, clock: Callable[[], float] = time.time):
        self.registry = registry
        self.interval_s = interval_s
        self.clock = clock
        self.states: Dict[str, DeviceState] = {}
        self.last_ts: Dict[str, int] = {}
        self.failures: Dict[str, int] = {}
        self._last_power_change: Dict[str, int] = {}
        self._last_mode_reverse: Dict[str, int] = {}

    async def poll_device(self, device: Device) -> Optional[DeviceState]:
        backend = self.registry.backend_for(device)
        if backend is None:
            return None
        try:
            st = await backend.read(device)
        except Exception:  # a single bad device never breaks the sweep
            st = None
        if st is None:
            self.failures[device.id] = self.failures.get(device.id, 0) + 1
            prev = self.states.get(device.id)
            if prev is not None:
                prev.online = False  # keep the last-known values but show it as offline
            return None
        self.failures[device.id] = 0
        self.states[device.id] = st
        self.last_ts[device.id] = int(self.clock())
        return st

    async def poll_once(self) -> None:
        await asyncio.gather(
            *(self.poll_device(d) for d in self.registry.devices), return_exceptions=True
        )

    def power_cooldown_remaining(self, device: Device) -> int:
        if device.type not in COMPRESSOR_TYPES:
            return 0
        t = self._last_power_change.get(device.id)
        return 0 if t is None else max(0, POWER_COOLDOWN_S - (int(self.clock()) - t))

    def mode_cooldown_remaining(self, device: Device) -> int:
        if device.type not in COMPRESSOR_TYPES:
            return 0
        t = self._last_mode_reverse.get(device.id)
        return 0 if t is None else max(0, MODE_REVERSE_COOLDOWN_S - (int(self.clock()) - t))

    async def apply(self, device: Device, command: Command) -> Dict[str, object]:
        """Apply a command, enforcing climate cooldowns server-side, then refresh the
        device's cached state so the response/UI reflects the change immediately."""
        backend = self.registry.backend_for(device)
        if backend is None:
            return {"ok": False, "error": "no backend for device"}

        cur = self.states.get(device.id)
        cur_mode = cur.mode if cur else None
        reversing = "mode" in command and _is_compressor_reverse(cur_mode, str(command["mode"]))

        if device.type in COMPRESSOR_TYPES:
            if "power" in command and self.power_cooldown_remaining(device) > 0:
                return {"ok": False, "cooldown": True, "retry_after": self.power_cooldown_remaining(device), "reason": "power"}
            if reversing and self.mode_cooldown_remaining(device) > 0:
                return {"ok": False, "cooldown": True, "retry_after": self.mode_cooldown_remaining(device), "reason": "mode_reverse"}

        res = await backend.apply(device, command)
        if res.get("ok"):
            now = int(self.clock())
            if device.type in COMPRESSOR_TYPES and "power" in command:
                self._last_power_change[device.id] = now
            if reversing:
                self._last_mode_reverse[device.id] = now
            await self.poll_device(device)
        return res

    async def run(self, stop_event: Optional[asyncio.Event] = None) -> None:
        while not (stop_event and stop_event.is_set()):
            try:
                await self.poll_once()
            except Exception:
                pass
            try:
                if stop_event:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.interval_s)
                else:
                    await asyncio.sleep(self.interval_s)
            except asyncio.TimeoutError:
                pass
