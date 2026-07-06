"""Solar-inverter (solarpi) backend field mapping + the inverter device model. Pure/stdlib."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon.backends import solarpi  # noqa: E402
from smartmon.devices import Device  # noqa: E402


def inv(**opts):
    return Device(id="inv", name="Inverter", type="inverter", protocol="solarpi", options=opts)


class TestMapCurrent(unittest.TestCase):
    # A trimmed but real-shaped SolarPi /api/current snapshot.
    SAMPLE = {"available": True, "ts": 1720200000, "pv_power": 2450.0, "battery_soc": 82,
              "battery_power": -300.0, "load_total": 900, "grid_voltage": 122.4}

    def test_maps_pv_battery_load(self):
        st = solarpi.map_current(inv(), self.SAMPLE)
        self.assertTrue(st.online)
        self.assertEqual(st.solar_power_w, 2450.0)   # pv_power -> the solar-trigger signal
        self.assertEqual(st.battery_percent, 82)
        self.assertEqual(st.load_w, 900.0)

    def test_unavailable_returns_none(self):
        self.assertIsNone(solarpi.map_current(inv(), {"available": False}))
        self.assertIsNone(solarpi.map_current(inv(), "not a dict"))

    def test_missing_fields_stay_none(self):
        st = solarpi.map_current(inv(), {"available": True, "pv_power": 100})
        self.assertEqual(st.solar_power_w, 100.0)
        self.assertIsNone(st.battery_percent)
        self.assertIsNone(st.load_w)

    def test_field_map_override(self):
        st = solarpi.map_current(inv(field_map={"solar_power": "pv_total"}),
                                 {"available": True, "pv_total": 3000})
        self.assertEqual(st.solar_power_w, 3000.0)

    def test_base_url_normalizes(self):
        self.assertEqual(solarpi.base_url(inv(url="http://pi.local:8000/"), "http://x"), "http://pi.local:8000")
        self.assertEqual(solarpi.base_url(inv(), "http://127.0.0.1:8000"), "http://127.0.0.1:8000")


class TestInverterDevice(unittest.TestCase):
    def test_inverter_needs_no_tuya_creds(self):
        d = Device.from_dict({"id": "inv", "name": "Inverter", "type": "inverter", "protocol": "solarpi"})
        self.assertEqual(d.type, "inverter")
        self.assertTrue(d.has("solar_power"))    # usable as a solar-trigger source
        self.assertTrue(d.has("battery"))
        self.assertFalse(d.has("power"))         # read-only: not a control target

    def test_inverter_options_roundtrip(self):
        d = Device.from_dict({"id": "inv", "name": "I", "type": "inverter", "protocol": "solarpi",
                              "options": {"url": "http://pi:8000"}})
        again = Device.from_dict(d.to_config_dict())
        self.assertEqual(again.option("url"), "http://pi:8000")
        self.assertEqual(again.protocol, "solarpi")

    def test_unknown_protocol_rejected(self):
        from smartmon.devices import DeviceConfigError
        with self.assertRaises(DeviceConfigError):
            Device.from_dict({"id": "x", "name": "X", "type": "inverter", "protocol": "modbus"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
