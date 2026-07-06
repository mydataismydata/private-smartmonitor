"""The poll loop and the control entry point.

Every `interval_s` it refreshes every device's state through its backend and caches
the result in memory (the API reads straight from this cache — there's no database in
phase 1). All control goes through `apply()`, which also enforces the one bit of
device-protection policy carried over from SolarPi: an A/C unit's compressor must not
be short-cycled, so on/off toggles and heat<->cool reversals on an `ac` or `solar_ac`
device are gated by a 5-minute cooldown. Plugs, lights, and switches toggle freely.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, Optional

from .backends.base import Command, DeviceState
from .devices import Device
from .registry import Registry

log = logging.getLogger("smartmon.control")  # control (write) actions only — polls are not logged

POWER_COOLDOWN_S = 300         # min seconds between an A/C unit's on/off changes
MODE_REVERSE_COOLDOWN_S = 300  # min seconds between heat<->cool switches (compressor reversal)
_COOLING_MODES = ("cool", "dry")  # cool + dry drive the compressor the same way; heat reverses it
# Types with a compressor to protect from short-cycling — both A/C variants.
COMPRESSOR_TYPES = ("ac", "solar_ac")


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
        # Optional async callback run once after every poll_once (the automation engine hooks
        # in here so routines are evaluated against fresh state each cycle). Set by the manager.
        self.cycle_hook: Optional[Callable[[], "asyncio.Future"]] = None

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
        """Apply a command, enforcing an A/C unit's compressor cooldowns server-side, then
        refresh the device's cached state so the response/UI reflects the change immediately."""
        backend = self.registry.backend_for(device)
        if backend is None:
            return {"ok": False, "error": "no backend for device"}

        cur = self.states.get(device.id)
        cur_mode = cur.mode if cur else None
        cur_power = cur.power if cur else None
        # A power write only counts (for gating and for arming the cooldown) when it actually
        # flips the unit's on/off state. The sheet sends a redundant power:true alongside a mode
        # change on an already-on unit; that's a no-op for the compressor and must not trip the
        # cooldown — otherwise switching e.g. Cool->Dry starts a countdown but never changes mode.
        switching_power = "power" in command and bool(command["power"]) != bool(cur_power)
        reversing = "mode" in command and _is_compressor_reverse(cur_mode, str(command["mode"]))
        # Every control action is logged (polls are not), so a mystery on/off can be traced to
        # whether — and when — this app sent a command: `journalctl --user -u smartmon | grep control`.
        log.info("control %s <- %s (was power=%s mode=%s; switching_power=%s reversing=%s)",
                 device.id, command, cur_power, cur_mode, switching_power, reversing)

        if device.type in COMPRESSOR_TYPES:
            if switching_power and self.power_cooldown_remaining(device) > 0:
                log.info("control %s BLOCKED by power cooldown (%ss left)", device.id, self.power_cooldown_remaining(device))
                return {"ok": False, "cooldown": True, "retry_after": self.power_cooldown_remaining(device), "reason": "power"}
            if reversing and self.mode_cooldown_remaining(device) > 0:
                log.info("control %s BLOCKED by mode-reverse cooldown (%ss left)", device.id, self.mode_cooldown_remaining(device))
                return {"ok": False, "cooldown": True, "retry_after": self.mode_cooldown_remaining(device), "reason": "mode_reverse"}

        res = await backend.apply(device, command)
        log.info("control %s applied %s -> ok=%s", device.id, command, res.get("ok"))
        if res.get("ok"):
            now = int(self.clock())
            if device.type in COMPRESSOR_TYPES and switching_power:
                self._last_power_change[device.id] = now
            if reversing:
                self._last_mode_reverse[device.id] = now
            # Refresh from the device for fresh metrics, then trust the command for the control
            # fields. Real Tuya units often echo their PRE-change dps on the read right after a
            # write (so power looks unchanged), and some mini-splits drop off Wi-Fi once powered
            # off (so every later read fails and the poller keeps the last-known ON). Either way the
            # device's report can't be trusted right after a control write — the command can.
            await self.poll_device(device)
            self._apply_command_to_state(device, command)
        return res

    def _apply_command_to_state(self, device: Device, command: Command) -> None:
        """Overlay a just-applied command's control fields onto the cached state, so the UI reflects
        the change immediately even when the device echoes a stale read or goes unreachable."""
        st = self.states.get(device.id)
        if st is None:
            st = DeviceState(online=True)
            self.states[device.id] = st
            self.last_ts[device.id] = int(self.clock())
        if "power" in command:
            st.power = bool(command["power"])
        if command.get("mode") is not None:
            st.mode = str(command["mode"])
        if command.get("fan") is not None:
            st.fan_speed = str(command["fan"])
        for key, attr in (("setpoint", "setpoint_c"), ("brightness", "brightness"), ("color_temp", "color_temp")):
            if key in command:
                try:
                    val = float(command[key])
                except (TypeError, ValueError):
                    continue
                setattr(st, attr, val if key == "setpoint" else int(round(val)))

    async def run(self, stop_event: Optional[asyncio.Event] = None) -> None:
        while not (stop_event and stop_event.is_set()):
            try:
                await self.poll_once()
            except Exception:
                pass
            if self.cycle_hook is not None:
                try:
                    await self.cycle_hook()
                except Exception:  # a bad automation never breaks the poll loop
                    pass
            try:
                if stop_event:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.interval_s)
                else:
                    await asyncio.sleep(self.interval_s)
            except asyncio.TimeoutError:
                pass
