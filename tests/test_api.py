"""Registry + poller + API payloads, including the climate anti-short-cycle cooldowns.
Pure/stdlib:  python tests/test_api.py
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon import api  # noqa: E402
from smartmon.backends.demo import demo_devices  # noqa: E402
from smartmon.devices import Device  # noqa: E402
from smartmon.poller import DevicePoller  # noqa: E402
from smartmon.registry import Registry  # noqa: E402


class FakeClock:
    def __init__(self, t=1000):
        self.t = t

    def __call__(self):
        return self.t


def climate_registry():
    devs = [Device(id="ac", name="AC", type="climate", protocol="demo",
                   options={"demo_power": True, "demo_mode": "cool", "demo_setpoint": 21})]
    return Registry(devs, demo=True)


class TestDevicesPayload(unittest.TestCase):
    def setUp(self):
        self.reg = Registry(demo_devices(), demo=True)
        self.poller = DevicePoller(self.reg, interval_s=10)
        asyncio.run(self.poller.poll_once())

    def test_payload_shape(self):
        p = api.devices_payload(self.reg, self.poller)
        self.assertTrue(p["demo"])
        self.assertEqual(len(p["devices"]), len(self.reg.devices))
        self.assertIn("rooms", p)
        self.assertIn("summary", p)

    def test_payload_has_state_and_no_secrets(self):
        for d in api.devices_payload(self.reg, self.poller)["devices"]:
            self.assertIn("state", d)
            self.assertIn("online", d)
            self.assertNotIn("local_key", d)

    def test_summary_counts_are_consistent(self):
        s = api.summary(self.reg.devices, self.poller)
        self.assertEqual(s["total"], len(self.reg.devices))
        self.assertEqual(s["on"] + s["off"], s["total"])
        self.assertGreaterEqual(s["on"], 1)

    def test_rooms_are_grouped(self):
        rooms = api.devices_payload(self.reg, self.poller)["rooms"]
        self.assertIn("Living Room", rooms)

    def test_command_updates_cache(self):
        light = next(d for d in self.reg.devices if d.type == "light")
        res = asyncio.run(self.poller.apply(light, {"power": True, "brightness": 25}))
        self.assertTrue(res["ok"])
        self.assertEqual(self.poller.states[light.id].brightness, 25)

    def test_one_device_payload_unknown(self):
        self.assertFalse(api.one_device_payload(self.reg, self.poller, "nope")["available"])


class TestClimateCooldown(unittest.TestCase):
    def test_power_cooldown_blocks_then_clears(self):
        clock = FakeClock()
        reg = climate_registry()
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]

        self.assertTrue(asyncio.run(poller.apply(ac, {"power": False}))["ok"])
        blocked = asyncio.run(poller.apply(ac, {"power": True}))
        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["cooldown"])
        self.assertEqual(blocked["reason"], "power")

        clock.t += 301  # past the 5-minute lockout
        self.assertTrue(asyncio.run(poller.apply(ac, {"power": True}))["ok"])

    def test_same_side_mode_switch_is_free(self):
        clock = FakeClock()
        reg = climate_registry()
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]
        # cool -> dry runs the compressor the same way: never gated
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "dry"}))["ok"])
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "cool"}))["ok"])

    def test_reversing_mode_switch_is_gated(self):
        clock = FakeClock()
        reg = climate_registry()
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]
        # cool -> heat reverses the compressor: allowed once, then locked out
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "heat"}))["ok"])
        blocked = asyncio.run(poller.apply(ac, {"mode": "cool"}))
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["reason"], "mode_reverse")
        clock.t += 301
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "cool"}))["ok"])

    def test_non_climate_has_no_cooldown(self):
        devs = [Device(id="plug", name="P", type="plug", protocol="demo")]
        reg = Registry(devs, demo=True)
        poller = DevicePoller(reg, interval_s=10)
        asyncio.run(poller.poll_once())
        plug = reg.by_id["plug"]
        for _ in range(4):  # rapid toggles are fine for a plug
            self.assertTrue(asyncio.run(poller.apply(plug, {"power": True}))["ok"])
            self.assertTrue(asyncio.run(poller.apply(plug, {"power": False}))["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
