"""DeviceManager — the mutable owner of the fleet behind the management UI.

The registry/poller were read-only in phase 1 (load smartmon.json at boot, poll them). This
wraps them so the UI can add/edit/remove devices at runtime: each change is validated,
persisted to smartmon.json (atomically, via store.py), and applied by rebuilding a live
registry and swapping it into the *running* poller — the poll loop reads `registry.devices`
each cycle, so no restart and no dropped task. Adding the first real device also flips the
app out of demo mode (demo devices aren't real config, so they're discarded on that flip).

All mutations are serialized by one lock. Edits that omit `local_key` keep the existing key,
so you never have to re-enter a secret just to rename a device or move it to another room.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from . import store
from .config import Config
from .devices import Device, DeviceConfigError
from .poller import DevicePoller
from .registry import Registry

# Fields the UI is allowed to set on a device (never the id — that's immutable).
_EDITABLE = ("name", "type", "protocol", "ip", "device_id")


class DeviceManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock: Optional[asyncio.Lock] = None  # created lazily so __init__ needn't run in a loop
        self.registry = Registry.from_config(cfg)
        self.poller = DevicePoller(self.registry, interval_s=cfg.poll_interval_s)

    def _get_lock(self) -> asyncio.Lock:
        # Bind the lock to the running loop on first use (Python 3.8-safe). The check+set is
        # synchronous, so concurrent coroutines can't race to create two locks.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def demo(self) -> bool:
        return self.registry.demo

    def get(self, device_id: str) -> Optional[Device]:
        return self.registry.by_id.get(device_id)

    def _configured(self) -> List[Device]:
        """The current persisted fleet. Empty while in demo — the demo fleet is a preview,
        not real config, so the first real add starts from a clean slate."""
        return [] if self.registry.demo else list(self.registry.devices)

    async def _commit(self, devices: List[Device]) -> None:
        """Persist the fleet, rebuild a live registry, and swap it into the running poller."""
        store.save_devices(self.cfg.devices_file, devices)
        new_reg = Registry(devices, demo=False, tuya_timeout=self.cfg.tuya_timeout_s)
        keep = {d.id for d in devices}
        for gone in [i for i in list(self.poller.states) if i not in keep]:
            self.poller.states.pop(gone, None)
            self.poller.last_ts.pop(gone, None)
            self.poller.failures.pop(gone, None)
        self.registry = new_reg
        self.poller.registry = new_reg
        await self.poller.poll_once()

    async def add(self, raw: Dict[str, object]) -> Dict[str, object]:
        async with self._get_lock():
            try:
                dev = Device.from_dict(raw)
            except (DeviceConfigError, ValueError) as e:
                return {"ok": False, "error": str(e)}
            devices = self._configured()
            if any(d.id == dev.id for d in devices):
                return {"ok": False, "error": "a device with id %r already exists" % dev.id}
            devices.append(dev)
            await self._commit(devices)
            return {"ok": True, "id": dev.id}

    async def update(self, device_id: str, raw: Dict[str, object]) -> Dict[str, object]:
        async with self._get_lock():
            devices = self._configured()
            idx = next((i for i, d in enumerate(devices) if d.id == device_id), None)
            if idx is None:
                return {"ok": False, "error": "unknown device"}
            try:
                merged = self._merge(devices[idx], raw)
            except (DeviceConfigError, ValueError) as e:
                return {"ok": False, "error": str(e)}
            devices[idx] = merged
            await self._commit(devices)
            return {"ok": True, "id": merged.id}

    async def remove(self, device_id: str) -> Dict[str, object]:
        async with self._get_lock():
            devices = self._configured()
            kept = [d for d in devices if d.id != device_id]
            if len(kept) == len(devices):
                return {"ok": False, "error": "unknown device"}
            await self._commit(kept)
            return {"ok": True, "id": device_id}

    def _merge(self, existing: Device, raw: Dict[str, object]) -> Device:
        """Overlay the submitted fields onto the existing config. Blank/omitted local_key
        keeps the stored key; id is never changed."""
        base = existing.to_config_dict()
        for key in _EDITABLE:
            if raw.get(key) not in (None, ""):
                base[key] = raw[key]
        if "room" in raw:  # room may legitimately be cleared
            base["room"] = raw["room"] or ""
        if raw.get("version"):
            base["version"] = raw["version"]
        if raw.get("local_key"):
            base["local_key"] = raw["local_key"]
        if "dps" in raw:
            base["dps"] = raw["dps"] or {}
        if "options" in raw:
            base["options"] = raw["options"] or {}
        base["id"] = existing.id
        return Device.from_dict(base)
