"""Registry + poller + API payloads, including the A/C anti-short-cycle cooldowns.
Pure/stdlib:  python tests/test_api.py
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon import api  # noqa: E402
from smartmon.backends.base import DeviceState  # noqa: E402
from smartmon.backends.demo import demo_devices  # noqa: E402
from smartmon.devices import Device  # noqa: E402
from smartmon.poller import DevicePoller  # noqa: E402
from smartmon.registry import Registry  # noqa: E402


class FakeClock:
    def __init__(self, t=1000):
        self.t = t

    def __call__(self):
        return self.t


def compressor_registry():
    # The solar mini-split is the only compressor-protected type.
    devs = [Device(id="ac", name="Mini-Split", type="solar_ac", protocol="demo",
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


class TestCompressorCooldown(unittest.TestCase):
    def test_power_cooldown_blocks_then_clears(self):
        clock = FakeClock()
        reg = compressor_registry()
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
        reg = compressor_registry()
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]
        # cool -> dry runs the compressor the same way: never gated
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "dry"}))["ok"])
        self.assertTrue(asyncio.run(poller.apply(ac, {"mode": "cool"}))["ok"])

    def test_mode_change_with_redundant_power_is_free(self):
        # Regression: the sheet sends {power:true, mode} on a mode tap. The unit is already on, so
        # that power write is a no-op and must neither arm nor be blocked by the power cooldown —
        # otherwise switching Cool->Dry starts a countdown but never actually changes the mode.
        clock = FakeClock()
        reg = compressor_registry()  # starts on + cool
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]

        self.assertTrue(asyncio.run(poller.apply(ac, {"power": True, "mode": "dry"}))["ok"])
        self.assertEqual(poller.power_cooldown_remaining(ac), 0)  # no bogus cooldown armed
        # and the mode actually took effect
        self.assertEqual(poller.states[ac.id].mode, "dry")
        # a second same-side switch right after is still free
        self.assertTrue(asyncio.run(poller.apply(ac, {"power": True, "mode": "cool"}))["ok"])
        self.assertEqual(poller.states[ac.id].mode, "cool")

    def test_reversing_mode_switch_is_gated(self):
        clock = FakeClock()
        reg = compressor_registry()
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

    def test_plain_ac_is_also_gated(self):
        # The gate covers BOTH A/C types, so a plain `ac` short-cycle is blocked too.
        clock = FakeClock()
        reg = Registry([Device(id="ac", name="A/C", type="ac", protocol="demo",
                               options={"demo_power": True})], demo=True)
        poller = DevicePoller(reg, interval_s=10, clock=clock)
        asyncio.run(poller.poll_once())
        ac = reg.by_id["ac"]
        self.assertTrue(asyncio.run(poller.apply(ac, {"power": False}))["ok"])
        self.assertTrue(asyncio.run(poller.apply(ac, {"power": True}))["cooldown"])

    def test_non_compressor_types_have_no_cooldown(self):
        # Plugs, switches, and lights toggle freely — only the A/C types are gated.
        devs = [
            Device(id="plug", name="P", type="plug", protocol="demo"),
            Device(id="fan", name="F", type="switch", protocol="demo"),
        ]
        reg = Registry(devs, demo=True)
        poller = DevicePoller(reg, interval_s=10)
        asyncio.run(poller.poll_once())
        for dev_id in ("plug", "fan"):
            dev = reg.by_id[dev_id]
            for _ in range(4):  # rapid toggles are fine
                self.assertTrue(asyncio.run(poller.apply(dev, {"power": True}))["ok"])
                self.assertTrue(asyncio.run(poller.apply(dev, {"power": False}))["ok"])


class _StaleBackend:
    """Simulates a Tuya unit whose read after a write lies: it keeps reporting power=ON (a stale
    echo, or the last-known value because it dropped off Wi-Fi once turned off)."""

    async def read(self, device):
        return DeviceState(online=True, power=True)  # always ON, regardless of what was applied

    async def apply(self, device, command):
        return {"ok": True}


class TestControlStateTrust(unittest.TestCase):
    def _poller(self):
        reg = Registry([Device(id="ac", name="AC", type="ac", protocol="demo",
                               options={"demo_power": True})], demo=True)
        reg._backends["demo"] = _StaleBackend()
        p = DevicePoller(reg, interval_s=10)
        asyncio.run(p.poll_once())  # seeds cache as ON via the stale read
        return p, reg.by_id["ac"]

    def test_off_sticks_even_when_device_reads_stale_on(self):
        # The bug: an automation/user turns the A/C off, but the post-write read echoes ON, so the
        # UI kept showing it on. The cache must trust the command over the stale read.
        poller, ac = self._poller()
        self.assertTrue(poller.states["ac"].power)                 # stale ON to start
        res = asyncio.run(poller.apply(ac, {"power": False}))
        self.assertTrue(res["ok"])
        self.assertFalse(poller.states["ac"].power)                # off sticks despite the stale read

    def test_control_fields_follow_command(self):
        poller, ac = self._poller()
        asyncio.run(poller.apply(ac, {"power": True, "mode": "cool", "setpoint": 21}))
        st = poller.states["ac"]
        self.assertEqual(st.mode, "cool")
        self.assertEqual(st.setpoint_c, 21)


if __name__ == "__main__":
    unittest.main(verbosity=2)
