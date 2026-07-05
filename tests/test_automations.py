"""Automation model + store (persistence/CRUD) + engine (edge/hysteresis/schedule).
Pure/stdlib:  python tests/test_automations.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmon import automations as A  # noqa: E402
from smartmon.backends.base import DeviceState  # noqa: E402


class FakeRegistry:
    def __init__(self, ids):
        self.by_id = {i: object() for i in ids}


def tc(epoch=1.0, minutes=420, weekday=0, day="2026-1"):
    return A.TimeContext(epoch, minutes, weekday, day)


def solar_state(w, online=True):
    s = DeviceState(online=online)
    s.solar_power_w = w
    return {"ac": s}


def temp_state(c, online=True):
    s = DeviceState(online=online)
    s.current_temp_c = c
    return {"ac": s}


class TestModel(unittest.TestCase):
    def test_schedule_from_dict_roundtrips(self):
        a = A.Automation.from_dict({
            "id": "morning", "name": "Morning", "enabled": True,
            "trigger": {"type": "schedule", "at": "07:30", "days": [0, 1, 2, 3, 4]},
            "action": {"device_id": "ac", "command": {"power": True, "mode": "cool", "setpoint": 22}},
        })
        again = A.Automation.from_dict(a.to_dict())
        self.assertEqual(again.trigger.at, "07:30")
        self.assertEqual(again.trigger.days, [0, 1, 2, 3, 4])
        self.assertEqual(again.action.command, {"power": True, "mode": "cool", "setpoint": 22})

    def test_solar_trigger_validates(self):
        a = A.Automation.from_dict({
            "id": "s", "name": "S",
            "trigger": {"type": "solar", "source": "ac", "comparator": "above", "value": 500},
            "action": {"device_id": "ac", "command": {"power": True}},
        })
        self.assertEqual(a.trigger.type, "solar")
        self.assertEqual(a.trigger.value, 500.0)

    def test_bad_time_rejected(self):
        with self.assertRaises(A.AutomationConfigError):
            A.Automation.from_dict({"id": "x", "name": "X",
                                    "trigger": {"type": "schedule", "at": "25:00"},
                                    "action": {"device_id": "ac", "command": {"power": True}}})

    def test_unknown_trigger_type_rejected(self):
        with self.assertRaises(A.AutomationConfigError):
            A.Automation.from_dict({"id": "x", "name": "X", "trigger": {"type": "motion"},
                                    "action": {"device_id": "ac", "command": {"power": True}}})

    def test_empty_command_rejected(self):
        with self.assertRaises(A.AutomationConfigError):
            A.Automation.from_dict({"id": "x", "name": "X",
                                    "trigger": {"type": "schedule", "at": "07:00"},
                                    "action": {"device_id": "ac", "command": {}}})

    def test_command_strips_unknown_keys(self):
        a = A.Automation.from_dict({"id": "x", "name": "X",
                                    "trigger": {"type": "schedule", "at": "07:00"},
                                    "action": {"device_id": "ac", "command": {"power": True, "bogus": 9}}})
        self.assertEqual(a.action.command, {"power": True})


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "automations.json")

    def _sample(self, aid="a1"):
        return {"id": aid, "name": "A", "trigger": {"type": "schedule", "at": "07:00"},
                "action": {"device_id": "ac", "command": {"power": True}}}

    def test_add_persists_and_reloads(self):
        store = A.AutomationStore([], path=self.path)
        self.assertTrue(store.add(self._sample())["ok"])
        reloaded = A.load_automations_file(self.path)
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].id, "a1")

    def test_duplicate_id_rejected(self):
        store = A.AutomationStore([], path=self.path)
        store.add(self._sample())
        self.assertFalse(store.add(self._sample())["ok"])

    def test_update_and_remove(self):
        store = A.AutomationStore([], path=self.path)
        store.add(self._sample())
        upd = dict(self._sample()); upd["name"] = "Renamed"
        self.assertTrue(store.update("a1", upd)["ok"])
        self.assertEqual(store.by_id["a1"].name, "Renamed")
        self.assertTrue(store.remove("a1")["ok"])
        self.assertEqual(store.automations, [])
        self.assertFalse(store.remove("a1")["ok"])

    def test_toggle(self):
        store = A.AutomationStore([], path=self.path)
        store.add(self._sample())
        self.assertFalse(store.toggle("a1", False)["enabled"])
        self.assertFalse(store.by_id["a1"].enabled)

    def test_from_config_demo_is_not_persisted(self):
        class Cfg:
            automations_file = os.path.join(self.dir, "nope.json")
            demo = True
        store = A.AutomationStore.from_config(Cfg())
        self.assertGreater(len(store.automations), 0)  # demo set
        self.assertIsNone(store.path)                  # preview only


class TestScheduleEngine(unittest.TestCase):
    def _engine(self, days=None):
        store = A.AutomationStore([A.Automation("s", "S",
            A.Trigger(type="schedule", at="07:00", days=days or []),
            A.Action(device_id="ac", command={"power": True}))])
        return A.AutomationEngine(store), FakeRegistry(["ac"])

    def test_fires_once_per_day(self):
        eng, reg = self._engine()
        self.assertTrue(eng.due(tc(minutes=420, day="2026-1"), {}, reg))          # 07:00 -> fire
        eng.mark_fired("s", tc(minutes=420, day="2026-1"))
        self.assertFalse(eng.due(tc(minutes=420, day="2026-1"), {}, reg))         # same day/time -> no
        self.assertTrue(eng.due(tc(minutes=420, day="2026-2"), {}, reg))          # next day -> fire

    def test_only_fires_at_the_minute(self):
        eng, reg = self._engine()
        self.assertFalse(eng.due(tc(minutes=419), {}, reg))  # 06:59
        self.assertTrue(eng.due(tc(minutes=420), {}, reg))   # 07:00

    def test_retries_within_the_minute_until_marked(self):
        # If the action can't apply on the first tick, due() keeps returning it until mark_fired.
        eng, reg = self._engine()
        self.assertTrue(eng.due(tc(minutes=420), {}, reg))
        self.assertTrue(eng.due(tc(minutes=420), {}, reg))  # not marked yet -> still due

    def test_day_filter(self):
        eng, reg = self._engine(days=[0])  # Monday only
        self.assertTrue(eng.due(tc(minutes=420, weekday=0), {}, reg))
        eng.mark_fired("s", tc(minutes=420, weekday=0, day="2026-1"))
        self.assertFalse(eng.due(tc(minutes=420, weekday=1, day="2026-2"), {}, reg))  # Tuesday


class TestLevelEngine(unittest.TestCase):
    def _engine(self, ttype="solar", comparator="above", value=500.0):
        store = A.AutomationStore([A.Automation("l", "L",
            A.Trigger(type=ttype, source="ac", comparator=comparator, value=value),
            A.Action(device_id="ac", command={"power": True, "mode": "cool"}))])
        return A.AutomationEngine(store), FakeRegistry(["ac"])

    def test_solar_rising_edge_and_hysteresis(self):
        eng, reg = self._engine()  # solar above 500, margin = max(25, 5%)=25 -> band floor 475
        self.assertFalse(eng.due(tc(), solar_state(400), reg))
        self.assertTrue(eng.due(tc(), solar_state(600), reg))    # cross -> fire
        self.assertFalse(eng.due(tc(), solar_state(650), reg))   # still above -> no re-fire
        self.assertFalse(eng.due(tc(), solar_state(480), reg))   # in band (>=475) -> still active
        self.assertFalse(eng.due(tc(), solar_state(470), reg))   # below band -> disarm
        self.assertTrue(eng.due(tc(), solar_state(600), reg))    # re-cross -> fire again

    def test_temperature_below_comparator(self):
        eng, reg = self._engine(ttype="temperature", comparator="below", value=20.0)  # margin 0.5
        self.assertFalse(eng.due(tc(), temp_state(22), reg))
        self.assertTrue(eng.due(tc(), temp_state(19), reg))      # drops below 20 -> fire
        self.assertFalse(eng.due(tc(), temp_state(20.4), reg))   # within band (<=20.5) -> active
        self.assertFalse(eng.due(tc(), temp_state(20.6), reg))   # above band -> disarm
        self.assertTrue(eng.due(tc(), temp_state(19), reg))      # re-cross -> fire

    def test_offline_source_does_not_fire(self):
        eng, reg = self._engine()
        self.assertFalse(eng.due(tc(), solar_state(900, online=False), reg))

    def test_disabled_never_fires(self):
        eng, reg = self._engine()
        eng.store.automations[0].enabled = False
        self.assertFalse(eng.due(tc(), solar_state(900), reg))

    def test_missing_target_device_yields_no_decision(self):
        eng, _ = self._engine()
        empty = FakeRegistry([])  # 'ac' not configured
        self.assertEqual(eng.due(tc(), solar_state(900), empty), [])

    def test_is_active_reflects_condition(self):
        eng, reg = self._engine()
        eng.due(tc(), solar_state(600), reg)
        self.assertTrue(eng.is_active("l"))
        eng.due(tc(), solar_state(100), reg)
        self.assertFalse(eng.is_active("l"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
