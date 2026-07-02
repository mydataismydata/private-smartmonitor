"""In-memory demo backend — a simulated fleet so the dashboard is fully interactive
with no hardware on the network.

This is the SmartMonitor analogue of SolarPi's inverter simulator: it lets the whole
stack (poll loop, API, dashboard) run and be clicked through on a laptop. Toggles and
sliders mutate the in-process state and stick; energy draw and room temperature get a
little live jitter so gauges breathe. State is per-process and resets on restart.
"""
from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, Iterable, Optional

from ..devices import Device
from .base import Backend, Command, DeviceState


class DemoBackend(Backend):
    def __init__(self, devices: Iterable[Device]):
        self._state: Dict[str, DeviceState] = {}
        self._base_w: Dict[str, float] = {}
        self._devices: Dict[str, Device] = {}
        for d in devices:
            self._devices[d.id] = d
            self._state[d.id] = self._seed(d)

    def _seed(self, device: Device) -> DeviceState:
        st = DeviceState(online=True, power=bool(device.option("demo_power", True)))
        if device.has("brightness"):
            st.brightness = int(device.option("demo_brightness", 60))
        if device.has("color_temp"):
            st.color_temp = int(device.option("demo_color_temp", 50))
        if device.has("energy"):
            base = float(device.option("demo_watts", 45))
            self._base_w[device.id] = base
            st.power_w = base if st.power else 0.0
        if device.has("setpoint"):
            st.setpoint_c = float(device.option("demo_setpoint", 21))
        if device.has("temperature"):
            st.current_temp_c = float(device.option("demo_temp", 23))
        if device.has("mode"):
            st.mode = str(device.option("demo_mode", "cool"))
        if device.has("fan"):
            speeds = device.fan_speeds
            st.fan_speed = str(device.option("demo_fan", speeds[0] if speeds else "auto"))
        if device.has("solar_power"):
            solar = float(device.option("demo_solar", 620)) if st.power else 0.0
            grid = float(device.option("demo_grid", 45)) if st.power else 0.0
            st.solar_power_w, st.grid_power_w = solar, grid
            total = solar + grid
            st.solar_percent = round(solar / total * 100) if total else 0
            st.grid_percent = 100 - st.solar_percent if total else 0
        return st

    def _get(self, device: Device) -> DeviceState:
        st = self._state.get(device.id)
        if st is None:
            st = self._seed(device)
            self._devices[device.id] = device
            self._state[device.id] = st
        return st

    async def read(self, device: Device) -> Optional[DeviceState]:
        st = self._get(device)
        out = replace(st, raw=dict(st.raw))
        # A touch of live jitter so the UI feels alive.
        if out.power_w is not None:
            base = self._base_w.get(device.id, 45.0)
            out.power_w = round(base + random.uniform(-4, 4), 1) if out.power else round(random.uniform(0, 1.5), 1)
        if out.current_temp_c is not None:
            out.current_temp_c = round(st.current_temp_c + random.uniform(-0.3, 0.3), 1)
        if out.solar_power_w is not None and out.power:
            out.solar_power_w = round(max(0.0, st.solar_power_w + random.uniform(-40, 40)), 0)
        if out.grid_power_w is not None and out.power:
            out.grid_power_w = round(max(0.0, st.grid_power_w + random.uniform(-8, 8)), 0)
        return out

    async def apply(self, device: Device, command: Command) -> Dict[str, object]:
        st = self._get(device)
        if "power" in command:
            st.power = bool(command["power"])
            if st.power_w is not None:
                st.power_w = self._base_w.get(device.id, 45.0) if st.power else 0.0
        if "brightness" in command and device.has("brightness"):
            st.brightness = max(0, min(100, int(round(float(command["brightness"])))))
        if "color_temp" in command and device.has("color_temp"):
            st.color_temp = max(0, min(100, int(round(float(command["color_temp"])))))
        if "setpoint" in command and device.has("setpoint"):
            st.setpoint_c = round(float(command["setpoint"]), 1)
        if "mode" in command and device.has("mode"):
            st.mode = str(command["mode"])
        if "fan" in command and device.has("fan"):
            st.fan_speed = str(command["fan"])
        return {"ok": True}


# A small, opinionated demo fleet spanning every device type and a few rooms — enough
# to populate the dashboard the way the mockups look. Used when no smartmon.json exists.
def demo_devices() -> list:
    specs = [
        ("living-lamp", "Living Room Lamp", "light", "Living Room", {"demo_brightness": 72}),
        ("living-tv", "TV & Media Plug", "plug", "Living Room", {"demo_watts": 130}),
        ("living-ac", "Living Mini-Split", "solar_ac", "Living Room",
         {"demo_mode": "cool", "demo_setpoint": 16, "demo_temp": 16, "demo_solar": 659, "demo_grid": 40,
          "demo_fan": "medium"}),
        ("kitchen-coffee", "Coffee Maker", "plug", "Kitchen", {"demo_power": False, "demo_watts": 950}),
        ("kitchen-lights", "Kitchen Lights", "light", "Kitchen", {"demo_brightness": 100}),
        ("bedroom-lamp", "Bedside Lamp", "light", "Bedroom", {"demo_power": False, "demo_brightness": 30}),
        ("bedroom-fan", "Bedroom Fan", "switch", "Bedroom", {}),
        ("office-desk", "Desk Setup Plug", "plug", "Office", {"demo_watts": 210}),
        ("garage-heater", "Garage Heater", "switch", "Garage", {"demo_power": False}),
        ("porch-lights", "Porch Lights", "light", "Outdoor", {"demo_power": False, "demo_brightness": 80}),
    ]
    from ..devices import Device
    return [
        Device(id=i, name=n, type=t, room=r, protocol="demo", options=o)
        for (i, n, t, r, o) in specs
    ]
