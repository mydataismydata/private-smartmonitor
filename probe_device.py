#!/usr/bin/env python3
"""Read-only probe: dump the live Tuya datapoints (DPs) each configured device reports.

Why this exists: the dashboard maps friendly A/C modes (Cool / Heat / Dry / Fan) onto the raw
enum strings your specific unit uses on DP 4. Those tokens vary by firmware. If a mode misbehaves
(e.g. tapping Dry sends the unit to Auto), it's because this unit's DP-4 token for that mode isn't
what the default assumes. This prints exactly what your unit reports right now, so the correct
value can be set instead of guessed.

It NEVER writes to a device — it only calls status().

Usage on the Pi, from the app directory (use the same Python the app runs with; if you use a
venv, e.g. `.venv/bin/python probe_device.py`):

    python3 probe_device.py            # every Tuya device in smartmon.json
    python3 probe_device.py living-ac  # just one device, by its id

To capture what your unit calls "Dry": set the unit to Dry with its IR remote (or the Smart Life
app), wait a few seconds, then run this — DP 4 will show the real token. If nothing can put the
unit in Dry, it has no Dry mode and the button should be removed for this unit.
"""
import json
import os
import sys
import time

MODE_DP = "4"    # operating mode enum (what Cool/Heat/Dry/Fan map onto)
FAN_DP = "23"    # fan speed enum


def find_config():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.environ.get("SMART_DEVICES_FILE"), "smartmon.json", os.path.join(here, "smartmon.json")):
        if p and os.path.exists(p):
            return p
    sys.exit("Could not find smartmon.json. Run this from the app directory (where smartmon.json lives), "
             "or set SMART_DEVICES_FILE=/path/to/smartmon.json.")


def load_devices(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("devices", data) if isinstance(data, dict) else data


def read_status(tinytuya, d):
    """status() with a couple of retries — the running service polls the same unit, so an
    occasional collision is normal; a retry clears it without stopping the service."""
    last = None
    for attempt in range(3):
        try:
            dev = tinytuya.Device(d["device_id"], d["ip"], d["local_key"], version=float(d.get("version", 3.3)))
            dev.set_socketTimeout(5)
            status = dev.status()
            if isinstance(status, dict) and isinstance(status.get("dps"), dict):
                return status["dps"], None
            last = status
        except Exception as e:  # noqa: BLE001 — diagnostic tool, surface whatever went wrong
            last = e
        time.sleep(1.5)
    return None, last


def main():
    want_id = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = find_config()
    print("Reading devices from:", cfg)
    devices = load_devices(cfg)
    try:
        import tinytuya
    except ImportError:
        sys.exit("tinytuya isn't installed for this Python. Use the same interpreter the app runs with "
                 "(inside its venv if it has one).")

    matched = 0
    for d in devices:
        if d.get("protocol") != "tuya":
            continue
        if want_id and d.get("id") != want_id:
            continue
        matched += 1
        print(f"\n=== {d.get('name')}  (id={d.get('id')}, type={d.get('type')})  @ {d.get('ip')} ===")
        dps, err = read_status(tinytuya, d)
        if dps is None:
            print("  ! could not read status():", err)
            print("    If it keeps failing, briefly stop the service, re-run, then start it:")
            print("      systemctl --user stop smartmon && python3 probe_device.py && systemctl --user start smartmon")
            continue
        for k in sorted(dps, key=lambda x: (len(x), x)):
            tag = ""
            if k == MODE_DP:
                tag = "   <-- MODE  (this is the token for the current operating mode)"
            elif k == FAN_DP:
                tag = "   <-- FAN speed"
            print(f"  DP {k:>4} = {dps[k]!r}{tag}")

    if not matched:
        print("\nNo matching Tuya device found in", cfg,
              "\n(Devices with protocol 'demo' have nothing to read.)")


if __name__ == "__main__":
    main()
