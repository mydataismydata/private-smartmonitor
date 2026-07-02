# Private SmartMonitor

A self-hosted controller for **smart plugs, lights, switches, and climate devices**, running
headless on a Raspberry Pi and served over the local network. It's a sibling of the
[Solar Tracking Dashboard](https://github.com/mydataismydata/solarpi) ("SolarPi") and shares its
shape — a FastAPI server that runs a background poll loop and serves a static dashboard — but where
SolarPi *reads* telemetry, this app *controls* a fleet of devices.

It runs on the **same Pi** as SolarPi, as a **separate service on port 8001** (SolarPi keeps 8000).

## Design

The dashboard follows the phone mockups in `.files/` — soft blue-gray canvas, white rounded cards,
teal on/off toggles, a circular control dial, mode buttons, sliders — **re-laid-out for a server**:
the phone's bottom-nav becomes a left rail, and the single-column card stacks become a responsive,
room-grouped grid. Light and dark themes are both included (light matches the mockups; it follows
your OS by default). A device card opens a thermostat-style control sheet:

- **light** → circular brightness dial + brightness / warm-cool sliders
- **plug** → live power-draw dial + on/off
- **climate** → setpoint dial, −/+ stepper, Cool/Heat/Auto/Dry/Fan/Off, room-temp readout
- **switch** → a big on/off

There's also an **Automation** tab (routines, matching the mockups) — see *Roadmap* for what's wired
vs. scaffolded.

## Device model

A device's `type` fixes its capabilities, which is what the UI renders controls from:

| Type      | Capabilities                          | Controls shown |
|-----------|---------------------------------------|----------------|
| `plug`    | power, energy                         | toggle + live watts |
| `switch`  | power                                 | toggle |
| `light`   | power, brightness, color_temp         | toggle + brightness/color sliders + dial |
| `climate` | power, mode, setpoint, temperature    | setpoint dial + stepper + mode buttons |

State flows one way: a **backend** reads a device into a `DeviceState` and applies plain command
dicts (`{"power": true}`, `{"brightness": 60}`, `{"mode": "cool", "setpoint": 21}`) to it. Adding a
new ecosystem later (TP-Link/Kasa, Hue, Zigbee-over-MQTT, …) is just another backend — nothing above
it changes.

### Backends

| Backend | What it does |
|---------|--------------|
| `tuya`  | Tuya-local (LAN, v3.x) control of plugs/lights/switches/climate. Generalized from SolarPi's read-only mini-split client into a read/write driver. Needs `tinytuya` (lazy-imported). |
| `demo`  | An in-memory simulated fleet, so the whole app runs and is clickable with **no hardware** — the SmartMonitor analogue of SolarPi's inverter simulator. |

## Layout

```
smartmon/
  config.py         env-var configuration (12-factor)
  devices.py        the Device model + capability map (pure)
  backends/
    base.py         DeviceState + the Backend interface
    tuya.py         Tuya-local driver + a pure, tested DP codec
    demo.py         in-memory simulator + the sample fleet
  registry.py       load smartmon.json (or the demo fleet) and wire up backends
  poller.py         poll loop + control entry point (climate anti-short-cycle policy)
  manager.py        add/edit/remove devices: validate, persist, hot-reload (demo->live)
  store.py          atomic writes of smartmon.json
  discovery.py      LAN scan for Tuya devices (tinytuya), lazy-imported
  automations.py    routines model + sample set (scaffold)
  api.py            JSON payload builders (pure, unit-tested)
  server.py         FastAPI: the JSON control + management API + serves the dashboard (production)
  devserver.py      stdlib http.server twin of the API (zero-install demo/dev)
  web/              static dashboard (vanilla JS, no framework)
tests/              pure-stdlib tests
smartmon.example.json  copy to smartmon.json for real hardware (git-ignored: holds keys)
```

## Running it

### Demo — zero install

Everything below the FastAPI layer is stdlib-only, so you can run the whole app on a bare Python:

```
python -m smartmon.devserver          # -> http://127.0.0.1:8001  (simulated fleet)
```

Click through the rooms, toggle devices, open the control sheets, flip the theme — it's all live
against an in-memory fleet. (This is also the `smartmon-demo` config in `.claude/launch.json`.)

### Tests — zero install

```
python tests/test_devices.py
python tests/test_api.py
```

Pure `unittest`; they cover the device model, the Tuya DP codec (both directions), the demo backend,
the API payloads, and the climate cooldowns.

### Production server (FastAPI)

```
pip install -r requirements.txt
uvicorn smartmon.server:app --host 0.0.0.0 --port 8001
```

With no `smartmon.json` present it serves the demo fleet; drop one in (below) to drive real hardware.

## Adding real devices

**From the dashboard (no file editing).** Click **Add device**, or **Scan network** to find Tuya
devices on the LAN and pre-fill their IP and device id — then paste the device's local key, pick a
type and room, and save. The first real device flips the app out of demo mode; add/edit/remove all
happen live, with no restart. Changes are written to `smartmon.json` next to the app, which is
**git-ignored** because it holds each device's local key. (You can still hand-write that file from
`smartmon.example.json` if you prefer.)

The fleet file looks like this — only `ip`, `device_id`, and `local_key` are required per Tuya
device; `dps` overrides DP numbers and `options` the scaling (`bright_scale`, `power_divisor`,
`temp_divisor`, `mode_map`) when a device deviates from the type defaults in `backends/tuya.py`:

```json
{
  "devices": [
    { "id": "living-lamp", "name": "Living Room Lamp", "room": "Living Room", "type": "light",
      "protocol": "tuya", "ip": "192.168.1.50", "device_id": "…", "local_key": "…", "version": 3.3 }
  ]
}
```

> The file is deliberately **not** named `devices.json` — that's tinytuya's own filename, and sharing
> it would let `tinytuya wizard`/`scan` read or overwrite your fleet.

### Getting a device's local key

Discovery finds a device's IP and id, but **not** its local key — Tuya encrypts that, and only your
Tuya account can reveal it. Extract keys once (same procedure SolarPi documents for the mini-split):

```
pip install tinytuya
python -m tinytuya wizard      # links your Smart Life / Tuya account, prints id + local key per device
```

Run the wizard in a scratch directory (not `~/smartmon`), since it writes its own `devices.json`.
Its live snapshot is also the moment to confirm DP numbers and scales against the defaults (e.g.
whether a light's brightness is 10..1000 or 25..255, or a plug's power is in watts or tenths).

> **The mini-split is shared, safely.** The EG4/Deye unit SolarPi reads is a Tuya device too, so it
> can appear here as a `climate` device (see `smartmon.example.json`). Tuya v3.3's LAN protocol allows
> a single connection at a time, so if both apps poll it, stagger their intervals or point
> SmartMonitor's climate control at it and let SolarPi read the split via SmartMonitor later.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/api/devices` | whole fleet, grouped by room, with a summary (no secrets) |
| GET    | `/api/devices/{id}` | one device |
| POST   | `/api/devices/{id}/command` | apply `{power?, brightness?, color_temp?, mode?, setpoint?}` |
| POST   | `/api/devices` | add a device (writes `smartmon.json`, flips to live) |
| PUT    | `/api/devices/{id}` | edit a device (omit `local_key` to keep the stored one) |
| DELETE | `/api/devices/{id}` | remove a device |
| GET    | `/api/devices/{id}/config` | editable config for the form (no local key) |
| GET    | `/api/discover` | LAN scan for Tuya devices (IP + id; needs `tinytuya`) |
| GET    | `/api/automations` | routines |
| POST   | `/api/automations/{id}/toggle` | enable/disable a routine |
| GET    | `/api/health` | liveness + device counts |

Climate on/off and heat↔cool reversals are rate-limited server-side (5-minute cooldown) to protect
the compressor; a blocked command returns `{"ok": false, "cooldown": true, "retry_after": <s>}`.

## Running on the Pi (alongside SolarPi)

Same recipe as SolarPi, on **port 8001** and a **user service named `smartmon`**.

```
git clone https://github.com/mydataismydata/private-smartmonitor.git ~/smartmon
cd ~/smartmon
git config core.hooksPath .githooks
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install tinytuya       # for real Tuya devices + network discovery
# then add devices from the dashboard (Add device / Scan network) — no file editing needed
```

`~/.config/systemd/user/smartmon.service`:

```ini
[Unit]
Description=Private SmartMonitor
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=%h/smartmon
ExecStart=%h/smartmon/.venv/bin/uvicorn smartmon.server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```
loginctl enable-linger
systemctl --user daemon-reload
systemctl --user enable --now smartmon
```

Live at **http://solarpi.local:8001** on your LAN. It advertises `_smartmon._tcp` over mDNS
(best-effort, via `zeroconf`).

### Deploying updates from your computer

`deploy.ps1` pushes local commits, then SSHes into the Pi to `git pull` and restart `smartmon`:

```powershell
.\deploy.ps1
.\deploy.ps1 -Pip        # also pip install (when requirements.txt changed)
```

## Roadmap

Built so far: the device model, Tuya-local + demo backends, the control API and dashboard
(Phase 1), and in-UI device management — add/edit/remove with LAN discovery and hot-reload
(Phase 2). Deliberately **not** built yet (so nothing pretends to work that doesn't):

- **Automation engine** — the routines tab is real and its toggles persist in memory, but the
  time/trigger loop that actually *fires* routines (driving `poller.apply`) is a later phase.
- **More backends** — TP-Link/Kasa, Hue, Zigbee-over-MQTT behind the same `Backend` interface.
- **History & energy** — a SQLite time-series of plug wattage (SolarPi's `db.py` is a ready model).
- **Auth** — it's LAN-only and unauthenticated today; add a token before exposing it off-LAN.
- **Cloud import** — the other onboarding path (pull the whole fleet + keys from your Tuya account).
