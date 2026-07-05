"""Automations (routines) — the Automation tab, now functional.

An automation is a **trigger** + an **action**:

  trigger  one of:
    schedule     — fire at HH:MM on chosen weekdays (once per day)
    solar        — fire when a device's PV power (DP 106) crosses a watts threshold
    temperature  — fire when a device's room temp (DP 3) crosses a °C threshold
  action   apply a command ({power, mode, setpoint, fan, brightness, ...}) to one device.

The engine is evaluated once per poll cycle. Level triggers (solar/temperature) are
**edge-triggered with hysteresis** so a value hovering around the threshold can't machine-gun
the device — crucial for the A/C compressor. Actions fire through poller.apply(), which still
enforces the anti-short-cycle cooldowns, so an automation can never short-cycle the compressor.

Model + engine are pure/stdlib (no asyncio, no network) so they unit-test on a bare Python; the
async firing lives in the poller/manager. Persistence mirrors devices: automations.json, written
atomically; absent file -> the demo set (in demo mode) or empty.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections import namedtuple
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

TRIGGER_TYPES = ("schedule", "solar", "temperature")
COMPARATORS = ("above", "below")
# Command keys an action may carry (subset of the device command vocabulary).
ACTION_KEYS = ("power", "mode", "setpoint", "fan", "brightness", "color_temp")

# The decomposed "now" the engine evaluates against — passed in so tests are timezone-independent
# and deterministic. minutes = minutes since local midnight; weekday 0=Mon..6=Sun; day_key is a
# per-calendar-day string used to fire a schedule at most once per day.
TimeContext = namedtuple("TimeContext", "epoch minutes weekday day_key")

# What the engine hands back to the poller: "apply this command to this device now."
Decision = namedtuple("Decision", "automation_id device command")


class AutomationConfigError(ValueError):
    """An automation entry is missing something required or is malformed."""


# ---- model --------------------------------------------------------------------

@dataclass
class Trigger:
    type: str
    at: str = ""                                    # schedule: "HH:MM" (24h)
    days: List[int] = field(default_factory=list)   # schedule: 0=Mon..6=Sun; [] = every day
    source: str = ""                                # solar/temperature: device id read from
    comparator: str = "above"                       # solar/temperature: "above" | "below"
    value: float = 0.0                              # solar: watts; temperature: °C
    hysteresis: float = 0.0                         # re-arm margin; 0 = sensible per-type default

    def to_dict(self) -> Dict[str, object]:
        if self.type == "schedule":
            return {"type": "schedule", "at": self.at, "days": list(self.days)}
        return {"type": self.type, "source": self.source, "comparator": self.comparator,
                "value": self.value, "hysteresis": self.hysteresis}


@dataclass
class Action:
    device_id: str = ""
    command: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {"device_id": self.device_id, "command": dict(self.command)}


@dataclass
class Automation:
    id: str
    name: str
    trigger: Trigger
    action: Action
    enabled: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {"id": self.id, "name": self.name, "enabled": self.enabled,
                "trigger": self.trigger.to_dict(), "action": self.action.to_dict()}

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "Automation":
        if not isinstance(raw, dict):
            raise AutomationConfigError("automation must be an object")
        aid = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not aid:
            raise AutomationConfigError("automation is missing an id")
        if not name:
            raise AutomationConfigError("automation %r is missing a name" % aid)
        trigger = _trigger_from_dict(raw.get("trigger") or {})
        action = _action_from_dict(raw.get("action") or {})
        enabled = bool(raw.get("enabled", True))
        return cls(id=aid, name=name, trigger=trigger, action=action, enabled=enabled)

    def public_dict(self, name_of: Optional[Callable[[str], str]] = None,
                    last_fired: Optional[float] = None,
                    active: Optional[bool] = None) -> Dict[str, object]:
        """Browser-facing view: config + resolved device names + runtime status. The UI builds the
        human-readable trigger/action summaries (so it can localize temperatures to °F)."""
        nm = name_of or (lambda d: d)
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "trigger": self.trigger.to_dict(),
            "action": self.action.to_dict(),
            "target_id": self.action.device_id,
            "target_name": nm(self.action.device_id) if self.action.device_id else "",
            "source_name": nm(self.trigger.source) if self.trigger.source else "",
            "last_fired": last_fired,
            "active": active,
        }


def _hhmm_to_minutes(at: str) -> int:
    parts = str(at).split(":")
    if len(parts) != 2:
        raise AutomationConfigError("schedule time must be HH:MM, got %r" % (at,))
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise AutomationConfigError("schedule time must be HH:MM, got %r" % (at,))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise AutomationConfigError("schedule time out of range: %r" % (at,))
    return h * 60 + m


def _trigger_from_dict(raw: Dict[str, object]) -> Trigger:
    ttype = str(raw.get("type") or "").strip()
    if ttype not in TRIGGER_TYPES:
        raise AutomationConfigError("trigger type must be one of %s" % (TRIGGER_TYPES,))
    if ttype == "schedule":
        at = str(raw.get("at") or "").strip()
        _hhmm_to_minutes(at)  # validate
        days = raw.get("days") or []
        if not isinstance(days, list) or any((not isinstance(d, int)) or d < 0 or d > 6 for d in days):
            raise AutomationConfigError("schedule days must be a list of ints 0..6 (Mon..Sun)")
        return Trigger(type="schedule", at=at, days=[int(d) for d in days])
    # solar / temperature
    source = str(raw.get("source") or "").strip()
    if not source:
        raise AutomationConfigError("%s trigger needs a 'source' device id" % ttype)
    comparator = str(raw.get("comparator") or "above").strip()
    if comparator not in COMPARATORS:
        raise AutomationConfigError("comparator must be 'above' or 'below'")
    try:
        value = float(raw.get("value"))
    except (TypeError, ValueError):
        raise AutomationConfigError("%s trigger needs a numeric 'value'" % ttype)
    try:
        hysteresis = float(raw.get("hysteresis", 0) or 0)
    except (TypeError, ValueError):
        hysteresis = 0.0
    return Trigger(type=ttype, source=source, comparator=comparator, value=value, hysteresis=hysteresis)


def _action_from_dict(raw: Dict[str, object]) -> Action:
    device_id = str(raw.get("device_id") or "").strip()
    if not device_id:
        raise AutomationConfigError("action needs a 'device_id'")
    cmd_in = raw.get("command") or {}
    if not isinstance(cmd_in, dict):
        raise AutomationConfigError("action 'command' must be an object")
    command = {k: cmd_in[k] for k in ACTION_KEYS if k in cmd_in}
    if not command:
        raise AutomationConfigError("action 'command' must set at least one of %s" % (ACTION_KEYS,))
    return Action(device_id=device_id, command=command)


# ---- persistence + store ------------------------------------------------------

def load_automations_file(path: str) -> List[Automation]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("automations") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise AutomationConfigError("automations file must be a list, or an object with an 'automations' list")
    autos = [Automation.from_dict(entry) for entry in raw]
    ids = [a.id for a in autos]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise AutomationConfigError("duplicate automation id(s): %s" % sorted(dupes))
    return autos


def save_automations(path: str, automations: List[Automation]) -> None:
    """Atomically write [Automation] to automations.json as {"automations": [...]}."""
    data = {"automations": [a.to_dict() for a in automations]}
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class AutomationStore:
    """The set of automations, with in-place CRUD. Persistence is optional: when `path` is set,
    every mutation is written through atomically. In demo mode `path` is None (the demo set is a
    preview, like the demo device fleet) so nothing is written."""

    def __init__(self, automations: List[Automation], path: Optional[str] = None):
        self.automations = automations
        self.path = path
        self.by_id: Dict[str, Automation] = {a.id: a for a in automations}

    @classmethod
    def from_config(cls, cfg) -> "AutomationStore":
        path = getattr(cfg, "automations_file", "automations.json")
        if os.path.exists(path):
            try:
                return cls(load_automations_file(path), path=path)
            except (OSError, AutomationConfigError, ValueError):
                pass  # unreadable/corrupt -> fall through to defaults rather than crash the app
        if getattr(cfg, "demo", False):
            return cls(demo_automations(), path=None)  # preview only, not persisted
        return cls([], path=path)  # real mode, no file yet: first add persists

    def _reindex(self) -> None:
        self.by_id = {a.id: a for a in self.automations}

    def _persist(self) -> None:
        if self.path:
            save_automations(self.path, self.automations)

    def add(self, raw: Dict[str, object]) -> Dict[str, object]:
        try:
            a = Automation.from_dict(raw)
        except (AutomationConfigError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        if a.id in self.by_id:
            return {"ok": False, "error": "an automation with id %r already exists" % a.id}
        self.automations.append(a)
        self._reindex()
        self._persist()
        return {"ok": True, "id": a.id}

    def update(self, automation_id: str, raw: Dict[str, object]) -> Dict[str, object]:
        idx = next((i for i, a in enumerate(self.automations) if a.id == automation_id), None)
        if idx is None:
            return {"ok": False, "error": "unknown automation"}
        merged = dict(raw)
        merged["id"] = automation_id  # id is immutable
        try:
            a = Automation.from_dict(merged)
        except (AutomationConfigError, ValueError) as e:
            return {"ok": False, "error": str(e)}
        self.automations[idx] = a
        self._reindex()
        self._persist()
        return {"ok": True, "id": a.id}

    def remove(self, automation_id: str) -> Dict[str, object]:
        kept = [a for a in self.automations if a.id != automation_id]
        if len(kept) == len(self.automations):
            return {"ok": False, "error": "unknown automation"}
        self.automations = kept
        self._reindex()
        self._persist()
        return {"ok": True, "id": automation_id}

    def toggle(self, automation_id: str, enabled: bool) -> Dict[str, object]:
        a = self.by_id.get(automation_id)
        if a is None:
            return {"ok": False, "error": "unknown automation"}
        a.enabled = bool(enabled)
        self._persist()
        return {"ok": True, "id": a.id, "enabled": a.enabled}


# ---- engine -------------------------------------------------------------------

@dataclass
class _Runtime:
    active: bool = False            # level triggers: currently inside the (hysteretic) condition
    last_fired_day: str = ""        # schedule: day_key it last fired (fire at most once/day)
    last_fired_epoch: float = 0.0


class AutomationEngine:
    """Evaluates the store's automations against the latest poll cache once per cycle and returns
    the actions that should fire. Holds per-automation edge-tracking state in memory (reset on
    restart — schedules simply won't back-fire a missed time, level triggers re-evaluate live)."""

    def __init__(self, store: AutomationStore):
        self.store = store
        self._rt: Dict[str, _Runtime] = {}

    def _runtime(self, aid: str) -> _Runtime:
        rt = self._rt.get(aid)
        if rt is None:
            rt = _Runtime()
            self._rt[aid] = rt
        return rt

    def last_fired(self, aid: str) -> Optional[float]:
        rt = self._rt.get(aid)
        return rt.last_fired_epoch if rt and rt.last_fired_epoch else None

    def is_active(self, aid: str) -> Optional[bool]:
        """For level triggers: whether the condition currently holds (drives a UI 'live' badge)."""
        a = self.store.by_id.get(aid)
        if a is None or a.trigger.type == "schedule":
            return None
        rt = self._rt.get(aid)
        return bool(rt.active) if rt else False

    @staticmethod
    def _margin(t: Trigger) -> float:
        if t.hysteresis:
            return abs(t.hysteresis)
        return max(25.0, 0.05 * abs(t.value)) if t.type == "solar" else 0.5  # temp: 0.5 °C

    def _value(self, t: Trigger, states) -> Optional[float]:
        st = states.get(t.source)
        if st is None or not getattr(st, "online", False):
            return None
        return st.solar_power_w if t.type == "solar" else st.current_temp_c

    def _level_holds(self, t: Trigger, val: float, active: bool) -> bool:
        """Threshold with hysteresis: enter at the threshold, don't leave until past the margin."""
        margin = self._margin(t)
        if t.comparator == "above":
            return val >= (t.value - margin) if active else val >= t.value
        return val <= (t.value + margin) if active else val <= t.value

    def _should_fire(self, a: Automation, rt: _Runtime, tc: TimeContext, states) -> bool:
        t = a.trigger
        if t.type == "schedule":
            matches = (tc.minutes == _hhmm_to_minutes(t.at)) and (not t.days or tc.weekday in t.days)
            return matches and rt.last_fired_day != tc.day_key
        val = self._value(t, states)
        if val is None:
            return False
        holds = self._level_holds(t, val, rt.active)
        rising = holds and not rt.active     # fire only on the rising edge
        rt.active = holds
        return rising

    def due(self, tc: TimeContext, states, registry) -> List[Decision]:
        """The automations that should fire this cycle, as (id, device, command). Mutates the
        per-automation edge state, so call it exactly once per poll cycle."""
        out: List[Decision] = []
        for a in self.store.automations:
            if not a.enabled:
                continue
            rt = self._runtime(a.id)
            if self._should_fire(a, rt, tc, states):
                dev = registry.by_id.get(a.action.device_id)
                if dev is not None and a.action.command:
                    out.append(Decision(a.id, dev, dict(a.action.command)))
        return out

    def mark_fired(self, aid: str, tc: TimeContext) -> None:
        """Record that an automation's action applied successfully (stops a schedule re-firing
        for the rest of the day; timestamps the 'last ran' the UI shows)."""
        rt = self._runtime(aid)
        rt.last_fired_day = tc.day_key
        rt.last_fired_epoch = tc.epoch


def now_context(epoch: float, localtime_struct) -> TimeContext:
    """Build a TimeContext from time.time() + time.localtime(). Kept here so the poller and tests
    construct it the same way."""
    lt = localtime_struct
    return TimeContext(
        epoch=epoch,
        minutes=lt.tm_hour * 60 + lt.tm_min,
        weekday=lt.tm_wday,
        day_key="%d-%d" % (lt.tm_year, lt.tm_yday),
    )


def demo_automations() -> List[Automation]:
    """Functional sample routines wired to the demo fleet — they actually fire against the
    DemoBackend, so the tab is live in the on-laptop demo."""
    return [
        Automation(
            id="free-cooling", name="Free Solar Cooling",
            trigger=Trigger(type="solar", source="living-ac", comparator="above", value=500),
            action=Action(device_id="living-ac", command={"power": True, "mode": "cool", "setpoint": 22}),
        ),
        Automation(
            id="too-warm", name="Cool When Warm",
            trigger=Trigger(type="temperature", source="living-ac", comparator="above", value=25.5),
            action=Action(device_id="living-ac", command={"power": True, "mode": "cool"}),
        ),
        Automation(
            id="lights-out", name="Porch Lights Off",
            trigger=Trigger(type="schedule", at="23:00", days=[]),
            action=Action(device_id="porch-lights", command={"power": False}),
            enabled=False,
        ),
    ]
