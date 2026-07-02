"""DeviceManager — add/edit/remove, persistence, and the demo->live flip. Pure/stdlib.

To stay fast and network-free, the CRUD flow uses protocol="demo" devices (a live registry
has no backend for them, so a commit's poll is a no-op — no sockets). Local-key preservation
is checked directly on the pure _merge(), with a real tuya device but still no network.

    python tests/test_manager.py
"""
import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon.config import Config  # noqa: E402
from smartmon.devices import Device  # noqa: E402
from smartmon.manager import DeviceManager  # noqa: E402
from smartmon.registry import load_devices_file  # noqa: E402


def demo_dev(dev_id, name, room="Room", dtype="plug"):
    return {"id": dev_id, "name": name, "type": dtype, "room": room, "protocol": "demo"}


class TestManagerCrud(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "smartmon.json")

    def _cfg(self):
        # No file yet -> demo mode; the first add should flip to live and create the file.
        return Config(devices_file=self.path, demo=not os.path.exists(self.path))

    def test_add_flips_demo_to_live_and_persists(self):
        async def scenario():
            m = DeviceManager(self._cfg())
            self.assertTrue(m.demo)
            r = await m.add(demo_dev("lamp", "Lamp"))
            return m, r

        m, r = asyncio.run(scenario())
        self.assertTrue(r["ok"])
        self.assertFalse(m.demo)                      # flipped to live
        self.assertTrue(os.path.exists(self.path))    # smartmon.json written
        saved = load_devices_file(self.path)
        self.assertEqual([d.id for d in saved], ["lamp"])

    def test_missing_id_rejected(self):
        async def scenario():
            m = DeviceManager(self._cfg())
            return await m.add({"name": "No Id", "type": "plug", "protocol": "demo"})

        self.assertFalse(asyncio.run(scenario())["ok"])

    def test_duplicate_id_rejected(self):
        async def scenario():
            m = DeviceManager(self._cfg())
            await m.add(demo_dev("lamp", "Lamp"))
            return await m.add(demo_dev("lamp", "Another Lamp"))

        self.assertFalse(asyncio.run(scenario())["ok"])

    def test_update_name_and_room(self):
        async def scenario():
            m = DeviceManager(self._cfg())
            await m.add(demo_dev("lamp", "Lamp", room="Hall"))
            r = await m.update("lamp", {"name": "Living Lamp", "room": "Living Room"})
            unknown = await m.update("nope", {"name": "x"})
            return r, unknown

        r, unknown = asyncio.run(scenario())
        self.assertTrue(r["ok"])
        self.assertFalse(unknown["ok"])
        saved = load_devices_file(self.path)
        self.assertEqual(saved[0].name, "Living Lamp")
        self.assertEqual(saved[0].room, "Living Room")

    def test_remove(self):
        async def scenario():
            m = DeviceManager(self._cfg())
            await m.add(demo_dev("a", "A"))
            await m.add(demo_dev("b", "B"))
            r = await m.remove("a")
            missing = await m.remove("a")  # already gone
            return r, missing

        r, missing = asyncio.run(scenario())
        self.assertTrue(r["ok"])
        self.assertFalse(missing["ok"])
        self.assertEqual([d.id for d in load_devices_file(self.path)], ["b"])

    def test_starts_live_when_file_present(self):
        async def scenario():
            m0 = DeviceManager(self._cfg())
            await m0.add(demo_dev("a", "A"))          # creates the file
            m1 = DeviceManager(self._cfg())           # fresh manager sees the file
            return m1

        m1 = asyncio.run(scenario())
        self.assertFalse(m1.demo)
        self.assertEqual([d.id for d in m1.registry.devices], ["a"])


class TestMergePreservesKey(unittest.TestCase):
    """_merge is pure — no loop / network needed."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.mgr = DeviceManager(Config(devices_file=os.path.join(self.dir, "d.json"), demo=True))
        self.dev = Device.from_dict({
            "id": "lamp", "name": "Lamp", "type": "light", "protocol": "tuya",
            "ip": "192.168.1.9", "device_id": "abc123", "local_key": "SECRETKEY0123456",
        })

    def test_omitted_key_is_preserved(self):
        merged = self.mgr._merge(self.dev, {"name": "New Name", "room": "Den"})
        self.assertEqual(merged.name, "New Name")
        self.assertEqual(merged.room, "Den")
        self.assertEqual(merged.local_key, "SECRETKEY0123456")  # unchanged
        self.assertEqual(merged.id, "lamp")                     # id immutable

    def test_provided_key_overrides(self):
        merged = self.mgr._merge(self.dev, {"local_key": "NEWKEY9876543210"})
        self.assertEqual(merged.local_key, "NEWKEY9876543210")

    def test_ip_and_type_editable(self):
        merged = self.mgr._merge(self.dev, {"ip": "192.168.1.22", "type": "plug"})
        self.assertEqual(merged.ip, "192.168.1.22")
        self.assertEqual(merged.type, "plug")


if __name__ == "__main__":
    unittest.main(verbosity=2)
