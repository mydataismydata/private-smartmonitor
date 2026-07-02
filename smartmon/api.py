"""Pure API payload builders over the registry + poll cache — no web framework here,
so they unit-test on a bare Python. server.py is a thin FastAPI adapter that calls
these (same split as SolarPi's api.py / server.py).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .automations import AutomationStore
from .backends.base import DeviceState
from .devices import Device, rooms_of
from .poller import DevicePoller
from .registry import Registry


def device_payload(device: Device, poller: DevicePoller) -> Dict[str, object]:
    """One device: browser-safe identity + capabilities + live state."""
    st = poller.states.get(device.id)
    out = device.public_dict()
    out["state"] = (st or DeviceState()).to_dict()
    out["online"] = bool(st.online) if st else False
    out["last_ts"] = poller.last_ts.get(device.id)
    if device.type == "climate":
        out["power_cooldown"] = poller.power_cooldown_remaining(device)
        out["mode_cooldown"] = poller.mode_cooldown_remaining(device)
    return out


def summary(devices: List[Device], poller: DevicePoller) -> Dict[str, object]:
    total = len(devices)
    on = 0
    offline = 0
    for d in devices:
        st = poller.states.get(d.id)
        if not st or not st.online:
            offline += 1
        if st and st.online and st.power:
            on += 1
    return {"total": total, "on": on, "off": total - on, "offline": offline}


def devices_payload(registry: Registry, poller: DevicePoller) -> Dict[str, object]:
    """The whole fleet, grouped by room, plus a headline summary for the greeting bar."""
    devices = registry.devices
    return {
        "demo": registry.demo,
        "rooms": rooms_of(devices),
        "summary": summary(devices, poller),
        "devices": [device_payload(d, poller) for d in devices],
    }


def one_device_payload(registry: Registry, poller: DevicePoller, device_id: str) -> Dict[str, object]:
    d = registry.by_id.get(device_id)
    if d is None:
        return {"available": False}
    out = device_payload(d, poller)
    out["available"] = True
    return out


def automations_payload(store: AutomationStore, registry: Registry) -> Dict[str, object]:
    def name_of(dev_id: str) -> str:
        d = registry.by_id.get(dev_id)
        return d.name if d else dev_id

    return {"automations": [a.public_dict(name_of) for a in store.automations]}


def device_config_payload(manager, device_id: str) -> Dict[str, object]:
    """The editable config for one device (no local key — never sent to the browser), for the
    edit form. Includes has_local_key so the form can show 'leave blank to keep'."""
    d = manager.get(device_id)
    if d is None:
        return {"available": False}
    out = d.editable_dict()
    out["available"] = True
    return out


def mark_discovered(manager, scan_result: Dict[str, object]) -> Dict[str, object]:
    """Annotate a discovery scan with which found devices are already configured, so the UI
    can dim the ones you've already added."""
    if not scan_result.get("available"):
        return scan_result
    configured = {d.device_id for d in manager.registry.devices if d.protocol == "tuya" and d.device_id}
    for entry in scan_result.get("devices", []):
        did = entry.get("device_id")
        entry["configured"] = bool(did) and did in configured
    return scan_result


def health_payload(registry: Registry, poller: DevicePoller) -> Dict[str, object]:
    return {
        "ok": True,
        "demo": registry.demo,
        "devices": len(registry.devices),
        "online": sum(1 for d in registry.devices if (poller.states.get(d.id) and poller.states[d.id].online)),
        "poll_interval_s": poller.interval_s,
    }
