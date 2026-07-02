"""Device model + Tuya codec + demo backend — all pure/stdlib, so this runs on a bare
Python with no installs:  python tests/test_devices.py
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon.backends import tuya  # noqa: E402
from smartmon.backends.demo import DemoBackend, demo_devices  # noqa: E402
from smartmon.devices import Device, DeviceConfigError  # noqa: E402


def tuya_dev(dtype, **kw):
    return Device(
        id=kw.get("id", "d"), name="d", type=dtype, protocol="tuya",
        ip="1.2.3.4", device_id="x", local_key="k",
        dps=kw.get("dps", {}), options=kw.get("options", {}),
    )


class TestDeviceModel(unittest.TestCase):
    def test_from_dict_ok(self):
        d = Device.from_dict({"id": "p1", "name": "Plug", "type": "plug", "protocol": "tuya",
                              "ip": "1.2.3.4", "device_id": "x", "local_key": "k"})
        self.assertEqual(d.type, "plug")
        self.assertIn("power", d.capabilities)
        self.assertIn("energy", d.capabilities)

    def test_tuya_requires_connection_details(self):
        with self.assertRaises(DeviceConfigError):
            Device.from_dict({"id": "p1", "type": "plug", "protocol": "tuya"})

    def test_unknown_type_rejected(self):
        with self.assertRaises(DeviceConfigError):
            Device.from_dict({"id": "x", "type": "toaster"})

    def test_missing_id_rejected(self):
        with self.assertRaises(DeviceConfigError):
            Device.from_dict({"type": "plug", "protocol": "demo"})

    def test_public_dict_hides_secrets(self):
        d = Device.from_dict({"id": "p1", "type": "plug", "protocol": "tuya",
                              "ip": "10.0.0.9", "device_id": "secret-id", "local_key": "secret-key"})
        pub = d.public_dict()
        for leaked in ("local_key", "device_id", "ip"):
            self.assertNotIn(leaked, pub)
        self.assertEqual(pub["capabilities"], ["power", "energy"])

    def test_editable_dict_omits_key_but_flags_it(self):
        d = Device.from_dict({"id": "p1", "type": "light", "protocol": "tuya",
                              "ip": "10.0.0.9", "device_id": "id", "local_key": "key"})
        ed = d.editable_dict()
        self.assertNotIn("local_key", ed)
        self.assertTrue(ed["has_local_key"])
        self.assertEqual(ed["ip"], "10.0.0.9")

    def test_config_dict_round_trips(self):
        raw = {"id": "c1", "name": "Climate", "type": "climate", "room": "Den", "protocol": "tuya",
               "ip": "10.0.0.5", "device_id": "did", "local_key": "lk", "version": 3.3,
               "dps": {"mode": "4"}, "options": {"mode_map": {"cool": "cold"}}}
        again = Device.from_dict(Device.from_dict(raw).to_config_dict())
        self.assertEqual(again.id, "c1")
        self.assertEqual(again.local_key, "lk")
        self.assertEqual(again.dps, {"mode": "4"})
        self.assertEqual(again.options, {"mode_map": {"cool": "cold"}})


class TestTuyaCodec(unittest.TestCase):
    def test_plug_decode_power_and_watts(self):
        st = tuya.decode(tuya_dev("plug"), {"1": True, "19": 1305})
        self.assertTrue(st.power)
        self.assertAlmostEqual(st.power_w, 130.5)  # DP 19 is deci-watts by default

    def test_plug_power_divisor_override(self):
        st = tuya.decode(tuya_dev("plug", options={"power_divisor": 1}), {"1": True, "19": 130})
        self.assertAlmostEqual(st.power_w, 130.0)

    def test_light_brightness_roundtrip(self):
        d = tuya_dev("light")
        self.assertEqual(tuya.decode(d, {"20": True, "22": 500}).brightness, 50)
        self.assertEqual(dict(tuya.encode(d, {"brightness": 50}))["22"], 500)

    def test_light_bright_scale_override(self):
        d = tuya_dev("light", options={"bright_scale": 255})
        self.assertEqual(tuya.decode(d, {"20": True, "22": 255}).brightness, 100)
        self.assertEqual(dict(tuya.encode(d, {"brightness": 100}))["22"], 255)

    def test_brightness_never_encodes_below_min(self):
        # brightness 0 must not be sent as 0 (that is what power=off is for)
        self.assertGreaterEqual(dict(tuya.encode(tuya_dev("light"), {"brightness": 0}))["22"], tuya.BRIGHT_MIN)

    def test_switch_encode_power(self):
        self.assertEqual(dict(tuya.encode(tuya_dev("switch"), {"power": True})), {"1": True})

    def test_climate_mode_map_both_ways(self):
        d = tuya_dev("climate", options={"mode_map": {"cool": "cold", "heat": "hot", "dry": "wet"}})
        st = tuya.decode(d, {"1": True, "4": "cold", "2": 21, "3": 23})
        self.assertEqual(st.mode, "cool")
        self.assertEqual(st.setpoint_c, 21)
        self.assertEqual(st.current_temp_c, 23)
        self.assertEqual(dict(tuya.encode(d, {"mode": "cool"}))["4"], "cold")

    def test_setpoint_encode_int(self):
        self.assertEqual(dict(tuya.encode(tuya_dev("climate"), {"setpoint": 21}))["2"], 21)

    def test_dp_override_wins(self):
        self.assertEqual(tuya.dp_for(tuya_dev("plug", dps={"power": "7"}), "power"), "7")

    def test_unsupported_command_dropped(self):
        # a switch has no brightness DP; encoding brightness yields nothing
        self.assertEqual(tuya.encode(tuya_dev("switch"), {"brightness": 50}), [])

    def test_missing_dp_stays_none(self):
        st = tuya.decode(tuya_dev("climate"), {"1": True})  # no temp DPs present
        self.assertIsNone(st.setpoint_c)
        self.assertIsNone(st.current_temp_c)


class TestDemoBackend(unittest.TestCase):
    def test_apply_then_read_light(self):
        devs = demo_devices()
        backend = DemoBackend(devs)
        light = next(d for d in devs if d.type == "light")
        asyncio.run(backend.apply(light, {"power": True, "brightness": 40}))
        st = asyncio.run(backend.read(light))
        self.assertTrue(st.online)
        self.assertTrue(st.power)
        self.assertEqual(st.brightness, 40)

    def test_plug_watts_track_power(self):
        devs = demo_devices()
        backend = DemoBackend(devs)
        plug = next(d for d in devs if d.type == "plug")
        asyncio.run(backend.apply(plug, {"power": True}))
        on = asyncio.run(backend.read(plug))
        self.assertTrue(on.power)
        self.assertGreater(on.power_w, 5)          # drawing power when on
        asyncio.run(backend.apply(plug, {"power": False}))
        off = asyncio.run(backend.read(plug))
        self.assertFalse(off.power)
        self.assertLess(off.power_w, 2)            # ~standby when off

    def test_climate_setpoint_and_mode(self):
        devs = demo_devices()
        backend = DemoBackend(devs)
        ac = next(d for d in devs if d.type == "climate")
        asyncio.run(backend.apply(ac, {"mode": "heat", "setpoint": 24}))
        st = asyncio.run(backend.read(ac))
        self.assertEqual(st.mode, "heat")
        self.assertEqual(st.setpoint_c, 24)


if __name__ == "__main__":
    unittest.main(verbosity=2)
