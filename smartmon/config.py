"""Runtime configuration from environment variables (12-factor style), mirroring
SolarPi's config.py.

Everything has a sane default, and the big one is DEMO: with no smartmon.json on
disk the app runs an in-memory demo fleet, so `uvicorn smartmon.server:app` just
works with no hardware. On the Pi, drop a smartmon.json next to the app (see
smartmon.example.json) or add devices from the dashboard, and it switches to the
real backends automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default) not in ("0", "false", "False", "")


@dataclass
class Config:
    # Where the device fleet is defined. Relative paths resolve against the CWD
    # (the service's WorkingDirectory on the Pi). Missing file -> demo mode.
    # NB: intentionally NOT "devices.json" — that's tinytuya's own file name, and sharing it would
    # let `tinytuya wizard`/`scan` read or overwrite the user's fleet. Keep them separate.
    devices_file: str = "smartmon.json"
    # Force the in-memory demo fleet even if a smartmon.json exists (handy for a
    # UI demo on your laptop). Auto-on when devices_file is absent.
    demo: bool = False
    # How often the poll loop refreshes every device's state.
    poll_interval_s: float = 10.0
    # Per-device socket timeout for the Tuya-local backend.
    tuya_timeout_s: float = 5.0
    # Port the dashboard is served on. uvicorn owns the actual bind; this value is
    # only used to advertise the right port over mDNS (_smartmon._tcp). Defaults to
    # 8001 so it sits alongside SolarPi (8000) on the same Pi without clashing.
    http_port: int = 8001

    @classmethod
    def from_env(cls) -> "Config":
        devices_file = os.environ.get("SMART_DEVICES_FILE", cls.devices_file)
        # Demo is explicit via SMART_DEMO, or implicit when no devices file is present.
        demo = _flag("SMART_DEMO") or not os.path.exists(devices_file)
        return cls(
            devices_file=devices_file,
            demo=demo,
            poll_interval_s=float(os.environ.get("SMART_POLL_INTERVAL", cls.poll_interval_s)),
            tuya_timeout_s=float(os.environ.get("SMART_TUYA_TIMEOUT", cls.tuya_timeout_s)),
            http_port=int(os.environ.get("SMART_HTTP_PORT", cls.http_port)),
        )
