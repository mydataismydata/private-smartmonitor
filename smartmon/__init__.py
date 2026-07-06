"""Private SmartMonitor — a self-hosted controller for smart plugs, lights,
switches, and A/C units, running headless on a Raspberry Pi.

It's a sibling of the Solar Tracking Dashboard ("SolarPi") and shares its shape:
a FastAPI server that runs a background poll loop and serves a static dashboard.
Where SolarPi *reads* one Tuya mini-split, this app *controls* a fleet of devices
through a small pluggable backend interface (Tuya-local today; more can slot in).

Phase 1: device model + Tuya-local / demo backends -> poll loop -> FastAPI +
dashboard. It ships pointing at an in-memory DEMO fleet, so it runs anywhere out
of the box; point it at real hardware with a smartmon.json (see smartmon.example.json).
"""

__version__ = "0.6.1"
