"""Zero-dependency dev / demo server (Python stdlib http.server only).

The production server is smartmon/server.py (FastAPI + uvicorn) — that's what runs on
the Pi. But every layer beneath it (devices, backends, poller, api) is stdlib-only, so
this module re-exposes the exact same JSON API and static dashboard using nothing but
http.server. You can therefore run and click through the whole app on a bare Python with
no `pip install` — which is how the UI is developed on Windows before deploying to the
Pi (SolarPi's tests are stdlib-only for the same reason).

    python -m smartmon.devserver          # -> http://127.0.0.1:8001

Always runs the in-memory demo fleet. For real hardware, use the FastAPI server.
"""
from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import api
from .automations import AutomationStore, demo_automations
from .config import Config
from .poller import DevicePoller
from .registry import Registry

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_COMMAND_KEYS = ("power", "brightness", "color_temp", "mode", "setpoint")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class App:
    """Holds the demo registry, poll cache, and automations for the process lifetime."""

    def __init__(self):
        cfg = Config.from_env()
        cfg.demo = True  # the dev server is always demo
        self.registry = Registry.from_config(cfg)
        self.poller = DevicePoller(self.registry, interval_s=cfg.poll_interval_s)
        self.automations = AutomationStore(demo_automations())
        asyncio.run(self.poller.poll_once())


APP: "App | None" = None


def app() -> App:
    global APP
    if APP is None:
        APP = App()
    return APP


class Handler(BaseHTTPRequestHandler):
    server_version = "SmartMonitorDev/0.1"

    def log_message(self, *args):  # keep the console quiet
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

    def do_GET(self):
        path = urlparse(self.path).path
        a = app()
        if path == "/api/devices":
            asyncio.run(a.poller.poll_once())  # refresh state each fetch for live feel
            return self._send(200, api.devices_payload(a.registry, a.poller))
        if path.startswith("/api/devices/"):
            dev_id = path[len("/api/devices/"):]
            dev = a.registry.by_id.get(dev_id)
            if dev is not None:
                asyncio.run(a.poller.poll_device(dev))
            return self._send(200, api.one_device_payload(a.registry, a.poller, dev_id))
        if path == "/api/automations":
            return self._send(200, api.automations_payload(a.automations, a.registry))
        if path == "/api/health":
            return self._send(200, api.health_payload(a.registry, a.poller))
        return self._serve_static(path)

    do_HEAD = do_GET

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        a = app()
        if path.startswith("/api/devices/") and path.endswith("/command"):
            dev_id = path[len("/api/devices/"):-len("/command")]
            dev = a.registry.by_id.get(dev_id)
            if dev is None:
                return self._send(200, {"ok": False, "error": "unknown device"})
            command = {k: body[k] for k in _COMMAND_KEYS if k in body}
            if not command:
                return self._send(200, {"ok": False, "error": "empty command"})
            return self._send(200, asyncio.run(a.poller.apply(dev, command)))
        if path.startswith("/api/automations/") and path.endswith("/toggle"):
            auto_id = path[len("/api/automations/"):-len("/toggle")]
            return self._send(200, a.automations.toggle(auto_id, bool(body.get("enabled"))))
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
    app()  # build the demo fleet up front
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"SmartMonitor demo server on http://127.0.0.1:{port}  (stdlib, demo mode — Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
