"""LAN discovery of Tuya devices.

Tuya devices broadcast their presence on the local network; tinytuya's scanner listens and
returns each device's IP, id (gwId), and protocol version. It does NOT return the local key —
that's the one thing only your Tuya account holds — so the UI uses a scan result to pre-fill the
IP/device-id/version and then asks you to paste the key.

Two wrinkles handled here:
  - tinytuya's scanner insists on reading a `devices.json` (its DEVICEFILE) from the working
    directory and expects *its own* schema. Our config file is separate (smartmon.json), but to be
    safe we point tinytuya's device-file at a nonexistent path for the duration of the scan so a
    stray/foreign devices.json can't crash discovery.
  - the blocking scan is pushed off the event loop, and tinytuya is imported lazily so discovery
    just reports "unavailable" when it isn't installed.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Dict

DEFAULT_SCANTIME = 5.0


def _version(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 3.3


def _scan_sync(scantime: float) -> Dict[str, object]:
    try:
        import tinytuya  # noqa: F401
        from tinytuya import scanner as sc
    except Exception:
        return {"available": False, "error": "tinytuya is not installed on the server"}

    saved = getattr(sc, "DEVICEFILE", None)
    try:
        sc.DEVICEFILE = os.path.join(tempfile.gettempdir(), "smartmon-discovery-none.json")
        found = sc.devices(
            verbose=False, scantime=scantime, poll=False, discover=True, assume_yes=True, tuyadevices=[]
        )
    except Exception as e:
        return {"available": False, "error": "scan failed: %s" % (e,)}
    finally:
        if saved is not None:
            sc.DEVICEFILE = saved

    devices = []
    for ip, info in (found or {}).items():
        if not isinstance(info, dict):
            continue
        devices.append({
            "ip": info.get("ip") or ip,
            "device_id": info.get("gwId") or info.get("id") or "",
            "version": _version(info.get("version")),
            "product_key": info.get("productKey") or "",
            "name": info.get("name") or "",
        })
    return {"available": True, "devices": devices}


async def scan(scantime: float = DEFAULT_SCANTIME) -> Dict[str, object]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _scan_sync, scantime)
