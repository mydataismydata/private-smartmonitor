"""FastAPI app: serves the dashboard and a small JSON control API, and runs the poll
loop as a background task. Thin adapter — payload logic lives in api.py (unit-tested),
device I/O in the backends, control policy in the poller.

Run (after `pip install -r requirements.txt`):
    uvicorn smartmon.server:app --host 0.0.0.0 --port 8001
With no devices.json present it serves the in-memory demo fleet; drop a devices.json
next to it (see devices.example.json) to drive real hardware.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI
from fastapi.staticfiles import StaticFiles

from . import api
from .automations import AutomationStore, demo_automations
from .config import Config
from .poller import DevicePoller
from .registry import Registry

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

# The command keys the API accepts on POST /api/devices/{id}/command. Anything else is dropped.
_COMMAND_KEYS = ("power", "brightness", "color_temp", "mode", "setpoint")


def _start_mdns(port: int):
    """Advertise the app as a `_smartmon._tcp` service so other devices on the LAN can
    discover it (sibling of SolarPi's `_solarpi._tcp`). Best-effort: returns
    (Zeroconf, ServiceInfo) or (None, None) if zeroconf isn't installed / registration fails."""
    try:
        import socket

        from zeroconf import ServiceInfo, Zeroconf

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # no packets sent; just picks the primary-route IP
            ip = s.getsockname()[0]
        finally:
            s.close()

        info = ServiceInfo(
            "_smartmon._tcp.local.",
            "SmartMonitor._smartmon._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"path": "/api"},
        )
        zc = Zeroconf()
        zc.register_service(info)
        return zc, info
    except Exception:
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config.from_env()
    registry = Registry.from_config(cfg)
    poller = DevicePoller(registry, interval_s=cfg.poll_interval_s)
    automations = AutomationStore(demo_automations())

    stop = asyncio.Event()
    task = asyncio.create_task(poller.run(stop))

    http_port = int(os.environ.get("SMART_HTTP_PORT", str(cfg.http_port)))
    zc, zc_info = _start_mdns(http_port)

    app.state.cfg = cfg
    app.state.registry = registry
    app.state.poller = poller
    app.state.automations = automations
    try:
        yield
    finally:
        if zc is not None:
            try:
                if zc_info is not None:
                    zc.unregister_service(zc_info)
                zc.close()
            except Exception:
                pass
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Private SmartMonitor", lifespan=lifespan)


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Revalidate static assets each load (ETag -> 304 if unchanged) so UI updates show
    up on a normal refresh without a hard-refresh."""
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/devices")
async def devices():
    return api.devices_payload(app.state.registry, app.state.poller)


@app.get("/api/devices/{device_id}")
async def device(device_id: str):
    return api.one_device_payload(app.state.registry, app.state.poller, device_id)


@app.post("/api/devices/{device_id}/command")
async def device_command(device_id: str, body: dict = Body(...)):
    """Apply a partial desired-state command, e.g. {"power": true}, {"brightness": 60},
    {"mode": "cool", "setpoint": 21}. Unknown keys are ignored; climate cooldowns are
    enforced server-side (see poller.apply)."""
    dev = app.state.registry.by_id.get(device_id)
    if dev is None:
        return {"ok": False, "error": "unknown device"}
    command = {k: body[k] for k in _COMMAND_KEYS if k in body}
    if not command:
        return {"ok": False, "error": "empty command"}
    return await app.state.poller.apply(dev, command)


@app.get("/api/automations")
async def automations():
    return api.automations_payload(app.state.automations, app.state.registry)


@app.post("/api/automations/{automation_id}/toggle")
async def automation_toggle(automation_id: str, enabled: bool = Body(..., embed=True)):
    return app.state.automations.toggle(automation_id, enabled)


@app.get("/api/health")
async def health():
    return api.health_payload(app.state.registry, app.state.poller)


# Static dashboard at / (registered last so /api/* wins). html=True serves index.html.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
