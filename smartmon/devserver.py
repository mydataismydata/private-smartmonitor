"""Zero-dependency dev / demo server (Python stdlib http.server only).

The production server is smartmon/server.py (FastAPI + uvicorn) — that's what runs on the Pi.
Everything beneath it (devices, backends, poller, manager, api) is stdlib-only, so this module
re-exposes the same JSON API + static dashboard using nothing but http.server. You can run and
click through the whole app — including adding/editing/removing devices — on a bare Python with
no `pip install`, which is how the UI is developed on Windows before deploying to the Pi.

    python -m smartmon.devserver          # -> http://127.0.0.1:8001

Respects Config like the real server: with no smartmon.json it serves the demo fleet; once you add
a device (which writes smartmon.json) it flips to live. LAN discovery needs `tinytuya` installed;
without it, discovery just reports unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import api, discovery
from .automations import AutomationStore, demo_automations
from .config import Config
from .manager import DeviceManager

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_COMMAND_KEYS = ("power", "brightness", "color_temp", "mode", "setpoint", "fan")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class _Bg:
    """A background asyncio loop. The DeviceManager (and its lock + poller) live entirely on
    this one loop, so every coroutine call must be marshalled here — using asyncio.run() per
    request would create a fresh loop each time and break the manager's lock."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


class App:
    def __init__(self):
        self.cfg = Config.from_env()
        self.bg = _Bg()
        self.manager = self.bg.run(self._build())
        self.automations = AutomationStore(demo_automations())
        self.bg.run(self.manager.poller.poll_once())

    async def _build(self) -> DeviceManager:
        # Built inside the bg loop so the manager's asyncio.Lock binds to that loop.
        return DeviceManager(self.cfg)


APP: "App | None" = None


def app() -> App:
    global APP
    if APP is None:
        APP = App()
    return APP


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartMonitorDev/0.2"

    def log_message(self, *args):
        pass

    def _send(self, code: int, body, ctype: str = "application/json"):
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        a = app()
        if path == "/api/devices":
            a.bg.run(a.manager.poller.poll_once())  # refresh each fetch for live feel
            return self._send(200, api.devices_payload(a.manager.registry, a.manager.poller))
        if path == "/api/discover":
            return self._send(200, api.mark_discovered(a.manager, a.bg.run(discovery.scan())))
        if path == "/api/automations":
            return self._send(200, api.automations_payload(a.automations, a.manager.registry))
        if path == "/api/health":
            return self._send(200, api.health_payload(a.manager.registry, a.manager.poller))
        if path.endswith("/config") and path.startswith("/api/devices/"):
            dev_id = path[len("/api/devices/"):-len("/config")]
            return self._send(200, api.device_config_payload(a.manager, dev_id))
        if path.startswith("/api/devices/"):
            dev_id = path[len("/api/devices/"):]
            dev = a.manager.get(dev_id)
            if dev is not None:
                a.bg.run(a.manager.poller.poll_device(dev))
            return self._send(200, api.one_device_payload(a.manager.registry, a.manager.poller, dev_id))
        return self._serve_static(path)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        a = app()
        if path == "/api/devices":
            return self._send(200, a.bg.run(a.manager.add(body)))
        if path.startswith("/api/devices/") and path.endswith("/command"):
            dev_id = path[len("/api/devices/"):-len("/command")]
            dev = a.manager.get(dev_id)
            if dev is None:
                return self._send(200, {"ok": False, "error": "unknown device"})
            command = {k: body[k] for k in _COMMAND_KEYS if k in body}
            if not command:
                return self._send(200, {"ok": False, "error": "empty command"})
            return self._send(200, a.bg.run(a.manager.poller.apply(dev, command)))
        if path.startswith("/api/automations/") and path.endswith("/toggle"):
            auto_id = path[len("/api/automations/"):-len("/toggle")]
            return self._send(200, a.automations.toggle(auto_id, bool(body.get("enabled"))))
        return self._send(404, {"ok": False, "error": "not found"})

    def do_PUT(self):
        path = urlparse(self.path).path
        a = app()
        if path.startswith("/api/devices/"):
            dev_id = path[len("/api/devices/"):]
            return self._send(200, a.bg.run(a.manager.update(dev_id, self._body())))
        return self._send(404, {"ok": False, "error": "not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        a = app()
        if path.startswith("/api/devices/"):
            dev_id = path[len("/api/devices/"):]
            return self._send(200, a.bg.run(a.manager.remove(dev_id)))
        return self._send(404, {"ok": False, "error": "not found"})

    def _serve_static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(os.path.normpath(WEB_DIR)) or not os.path.isfile(full):
            full = os.path.join(WEB_DIR, "index.html")  # SPA fallback
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(full)[1].lower()
        self._send(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))


def main():
    port = int(os.environ.get("SMART_HTTP_PORT", "8001"))
    app()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    mode = "demo" if app().manager.demo else "live"
    print(f"SmartMonitor dev server on http://127.0.0.1:{port}  (stdlib, {mode} mode — Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
