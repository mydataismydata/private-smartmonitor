"""FastAPI app: serves the dashboard and a JSON control + management API, and runs the poll
loop as a background task. Thin adapter — payload logic lives in api.py (unit-tested), device
I/O in the backends, control policy in the poller, and add/edit/remove in the DeviceManager.

Run (after `pip install -r requirements.txt`):
    uvicorn smartmon.server:app --host 0.0.0.0 --port 8001
With no smartmon.json present it serves the in-memory demo fleet; add a device from the UI (or
drop in a smartmon.json) to drive real hardware.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, discovery
from .automations import AutomationStore, demo_automations
from .config import Config
from .manager import DeviceManager

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

# Command keys accepted on POST /api/devices/{id}/command. Anything else is dropped.
_COMMAND_KEYS = ("power", "brightness", "color_temp", "mode", "setpoint")


def _start_mdns(port: int):
    """Advertise the app as a `_smartmon._tcp` service (sibling of SolarPi's `_solarpi._tcp`).
    Best-effort: returns (Zeroconf, ServiceInfo) or (None, None) if zeroconf is missing."""
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
    manager = DeviceManager(cfg)
    automations = AutomationStore(demo_automations())

    stop = asyncio.Event()
    task = asyncio.create_task(manager.poller.run(stop))

    http_port = int(os.environ.get("SMART_HTTP_PORT", str(cfg.http_port)))
    zc, zc_info = _start_mdns(http_port)

    app.state.cfg = cfg
    app.state.manager = manager
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
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---- read / control -----------------------------------------------------------

@app.get("/api/devices")
async def devices():
    m = app.state.manager
    return api.devices_payload(m.registry, m.poller)


@app.get("/api/devices/{device_id}")
async def device(device_id: str):
    m = app.state.manager
    return api.one_device_payload(m.registry, m.poller, device_id)


@app.get("/api/devices/{device_id}/config")
async def device_config(device_id: str):
    return api.device_config_payload(app.state.manager, device_id)


@app.post("/api/devices/{device_id}/command")
async def device_command(device_id: str, body: dict = Body(...)):
    m = app.state.manager
    dev = m.get(device_id)
    if dev is None:
        return {"ok": False, "error": "unknown device"}
    command = {k: body[k] for k in _COMMAND_KEYS if k in body}
    if not command:
        return {"ok": False, "error": "empty command"}
    return await m.poller.apply(dev, command)


# ---- manage (add / edit / remove / discover) ----------------------------------

@app.post("/api/devices")
async def add_device(body: dict = Body(...)):
    return await app.state.manager.add(body)


@app.put("/api/devices/{device_id}")
async def update_device(device_id: str, body: dict = Body(...)):
    return await app.state.manager.update(device_id, body)


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: str):
    return await app.state.manager.remove(device_id)


@app.get("/api/discover")
async def discover():
    return api.mark_discovered(app.state.manager, await discovery.scan())


# ---- automations --------------------------------------------------------------

@app.get("/api/automations")
async def automations():
    return api.automations_payload(app.state.automations, app.state.manager.registry)


@app.post("/api/automations/{automation_id}/toggle")
async def automation_toggle(automation_id: str, enabled: bool = Body(..., embed=True)):
    return app.state.automations.toggle(automation_id, enabled)


@app.get("/api/health")
async def health():
    m = app.state.manager
    return api.health_payload(m.registry, m.poller)


# Static dashboard at / (registered last so /api/* wins). html=True serves index.html.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
