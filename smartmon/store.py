"""Persist the device fleet to smartmon.json.

Loading lives in registry.load_devices_file; this is the write side, used when the UI
adds/edits/removes a device. Writes are atomic (temp file + os.replace) so a crash
mid-write can't leave a half-written smartmon.json that would fail to parse on restart.

smartmon.json holds Tuya local keys, so it's git-ignored — it only ever lives on the box
that runs the app.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import List

from .devices import Device


def save_devices(path: str, devices: List[Device]) -> None:
    """Atomically write [Device] to smartmon.json as {"devices": [...]}."""
    data = {"devices": [d.to_config_dict() for d in devices]}
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)  # atomic on POSIX and Windows
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
