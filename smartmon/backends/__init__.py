"""Device backends: the thin layer that turns a Device + a command into real I/O,
and a device's raw signals into a DeviceState.

- base.py  the DeviceState dataclass and the Backend interface
- tuya.py  Tuya-local (LAN) control, generalized from SolarPi's mini-split client
- demo.py  an in-memory simulator so the app runs with no hardware
"""
