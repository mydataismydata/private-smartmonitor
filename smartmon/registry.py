"""Load the device fleet and wire each device to a backend.

Source of truth is smartmon.json (see smartmon.example.json). If it's absent — or
SMART_DEMO=1 — we fall back to the in-memory demo fleet so the app always runs.
In demo mode every device is driven by the DemoBackend regardless of its declared
protocol, so you can point at a real smartmon.json but preview it without touching
the hardware.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from .backends.base import Backend
from .backends.demo import DemoBackend, demo_devices
from .backends.solarpi import SolarPiBackend
from .backends.tuya import TuyaBackend
from .config import Config
from .devices import Device, DeviceConfigError


def load_devices_file(path: str) -> List[Device]:
    """Parse smartmon.json -> [Device]. Raises DeviceConfigError on malformed entries."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("devices") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise DeviceConfigError("devices file must be a list, or an object with a 'devices' list")
    devices = [Device.from_dict(entry) for entry in raw]
    ids = [d.id for d in devices]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise DeviceConfigError(f"duplicate device id(s): {sorted(dupes)}")
    return devices


class Registry:
    """Holds the loaded devices plus one backend instance per protocol in use, and
    resolves the right backend for any device."""

    def __init__(self, devices: List[Device], demo: bool, tuya_timeout: float = 5.0,
                 solarpi_url: str = "http://127.0.0.1:8000"):
        self.devices = devices
        self.demo = demo
        self.by_id: Dict[str, Device] = {d.id: d for d in devices}
        self._backends: Dict[str, Backend] = {}
        if demo:
            self._backends["demo"] = DemoBackend(devices)
        if any(d.protocol == "tuya" for d in devices):
            self._backends["tuya"] = TuyaBackend(timeout=tuya_timeout)
        if any(d.protocol == "solarpi" for d in devices):
            self._backends["solarpi"] = SolarPiBackend(default_url=solarpi_url, timeout=tuya_timeout)

    def backend_for(self, device: Device) -> Optional[Backend]:
        proto = "demo" if self.demo else device.protocol
        return self._backends.get(proto)

    @classmethod
    def from_config(cls, cfg: Config) -> "Registry":
        if cfg.demo:
            # Demo mode: use a real smartmon.json if one exists (simulated), else the sample fleet.
            try:
                devices = load_devices_file(cfg.devices_file)
            except (OSError, DeviceConfigError, ValueError):
                devices = demo_devices()
            return cls(devices, demo=True, tuya_timeout=cfg.tuya_timeout_s, solarpi_url=cfg.solarpi_url)
        devices = load_devices_file(cfg.devices_file)
        return cls(devices, demo=False, tuya_timeout=cfg.tuya_timeout_s, solarpi_url=cfg.solarpi_url)
