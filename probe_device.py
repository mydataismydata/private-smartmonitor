#!/usr/bin/env python3
"""Discover what Tuya tokens a device actually uses on DP 4 (mode) / DP 23 (fan) — remotely.

The dashboard maps friendly A/C modes (Cool/Heat/Dry/Fan) onto raw enum tokens that vary by
firmware. Cool works on this unit ("cold"), Dry doesn't ("wet" is rejected -> Auto), so this unit
calls Dry something else (or has no Dry). This finds the real token without anyone touching the
unit. Three things, most-useful first:

  1. CLOUD SCHEMA (read-only, no device interaction): if `tinytuya wizard` left cloud creds
     (tinytuya.json) on this box, query Tuya's API for the device's `mode` enum — the definitive
     list of tokens the unit accepts. This alone usually answers it.
  2. LOCAL STATUS (read-only): dump the unit's current DPs over the LAN.
  3. ACTIVE PROBE (writes, opt-in via --find-dry): try candidate Dry tokens on DP 4, keep the one
     that sticks, then restore the original mode. Stays within the cooling family, so it never
     reverses the compressor or cycles power.

Usage on the Pi, from ~/smartmon, with the venv Python (it has tinytuya):

    .venv/bin/python probe_device.py                 # cloud schema + local status for all devices
    .venv/bin/python probe_device.py living-ac       # just one device id
    .venv/bin/python probe_device.py living-ac --find-dry   # actively find the Dry token

Paste the output back. The `mode` enum (step 1) or the discovered token (step 3) is all I need.
"""
import json
import os
import sys
import time

MODE_DP = "4"
FAN_DP = "23"
# Candidate Dry tokens seen across Tuya A/C firmwares (all cooling-family — none reverse the
# compressor). "wet" is the default that already failed on this unit; the rest are the usual
# alternates.
DRY_CANDIDATES = ["dehumidification", "dehumidify", "dry", "arefaction", "moisture", "wet"]


def find_config():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.environ.get("SMART_DEVICES_FILE"), "smartmon.json", os.path.join(here, "smartmon.json")):
        if p and os.path.exists(p):
            return p
    sys.exit("Could not find smartmon.json. Run this from the app directory, or set SMART_DEVICES_FILE.")


def load_devices(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("devices", data) if isinstance(data, dict) else data


def _enum_range(values):
    """Tuya function 'values' is a JSON string like '{\"range\":[...]}' — pull the list out."""
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            return None
    if isinstance(values, dict):
        return values.get("range")
    return None


def cloud_schema(tinytuya, device_id):
    """Return {code: [enum tokens]} for the device's enum functions, via the Tuya cloud API.
    Requires tinytuya.json (cloud creds) next to this script; returns None if unavailable."""
    if not any(os.path.exists(p) for p in ("tinytuya.json",
               os.path.join(os.path.dirname(os.path.abspath(__file__)), "tinytuya.json"))):
        return None, "no tinytuya.json (cloud creds) found - skipping cloud schema"
    try:
        c = tinytuya.Cloud()
    except Exception as e:  # noqa: BLE001
        return None, f"cloud init failed: {e}"
    out = {}
    try:
        for getter in ("getfunctions", "getproperties"):
            fn = getattr(c, getter, None)
            if not fn:
                continue
            resp = fn(device_id)
            result = resp.get("result", {}) if isinstance(resp, dict) else {}
            for key in ("functions", "status"):
                for item in (result.get(key) or []):
                    code, rng = item.get("code"), _enum_range(item.get("values"))
                    if code and rng and code not in out:
                        out[code] = rng
    except Exception as e:  # noqa: BLE001
        return None, f"cloud query failed: {e}"
    return out, None


def read_dps(tinytuya, d):
    last = None
    for _ in range(3):
        try:
            dev = tinytuya.Device(d["device_id"], d["ip"], d["local_key"], version=float(d.get("version", 3.3)))
            dev.set_socketTimeout(5)
            st = dev.status()
            if isinstance(st, dict) and isinstance(st.get("dps"), dict):
                return st["dps"], None
            last = st
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.5)
    return None, last


def find_dry(tinytuya, d):
    """Actively try each candidate Dry token; keep whichever the unit adopts; restore original."""
    dps, err = read_dps(tinytuya, d)
    if not dps:
        print("  ! can't read starting state, aborting active probe:", err)
        return
    original = dps.get(MODE_DP)
    print(f"  starting mode (DP4) = {original!r}; trying candidates (restoring to {original!r} after)...")
    dev = tinytuya.Device(d["device_id"], d["ip"], d["local_key"], version=float(d.get("version", 3.3)))
    dev.set_socketTimeout(5)
    winner = None
    for token in DRY_CANDIDATES:
        if token == original:
            continue
        try:
            dev.set_value(MODE_DP, token)
        except Exception as e:  # noqa: BLE001
            print(f"    {token!r:20} -> write error: {e}")
            continue
        time.sleep(3)
        back, _ = read_dps(tinytuya, d)
        got = back.get(MODE_DP) if back else None
        stuck = (got == token)
        print(f"    sent {token!r:20} -> unit now reports {got!r}{'   <-- ACCEPTED' if stuck else ''}")
        if stuck:
            winner = token
            break
    # restore
    try:
        if original is not None:
            dev.set_value(MODE_DP, original)
            print(f"  restored mode to {original!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not restore original mode {original!r}: {e} — set it from the dashboard.")
    if winner:
        print(f"\n  >>> This unit's Dry token is {winner!r}. Tell me and I'll wire it in.")
    else:
        print("\n  >>> No candidate stuck - this unit likely has no Dry mode on DP 4. "
              "I'll remove the Dry button for it.")


def main():
    args = sys.argv[1:]
    active = "--find-dry" in args
    ids = [a for a in args if not a.startswith("-")]
    want_id = ids[0] if ids else None

    cfg = find_config()
    print("Reading devices from:", cfg)
    devices = load_devices(cfg)
    try:
        import tinytuya
    except ImportError:
        sys.exit("tinytuya isn't installed for this Python. Use the venv: .venv/bin/python probe_device.py")

    matched = 0
    for d in devices:
        if d.get("protocol") != "tuya" or (want_id and d.get("id") != want_id):
            continue
        matched += 1
        print(f"\n=== {d.get('name')}  (id={d.get('id')}, type={d.get('type')})  @ {d.get('ip')} ===")

        schema, note = cloud_schema(tinytuya, d["device_id"])
        if schema:
            mode_vals = schema.get("mode") or schema.get("Mode")
            fan_vals = schema.get("fan_speed_enum") or schema.get("fan_speed") or schema.get("windspeed")
            print("  CLOUD SCHEMA:")
            print(f"    mode  (DP4)  accepts: {mode_vals}")
            print(f"    fan          accepts: {fan_vals}")
            if not mode_vals:
                print(f"    (no 'mode' enum in schema; full enum set: {schema})")
        elif note:
            print("  CLOUD SCHEMA:", note)

        dps, err = read_dps(tinytuya, d)
        if dps:
            print("  LIVE DPs:")
            for k in sorted(dps, key=lambda x: (len(x), x)):
                tag = "   <-- MODE" if k == MODE_DP else ("   <-- FAN" if k == FAN_DP else "")
                print(f"    DP {k:>4} = {dps[k]!r}{tag}")
        else:
            print("  ! could not read live DPs:", err)

        if active and d.get("type") in ("ac", "solar_ac"):
            print("  ACTIVE DRY PROBE:")
            find_dry(tinytuya, d)

    if not matched:
        print("\nNo matching Tuya device found in", cfg)


if __name__ == "__main__":
    main()
