"""Automations (routines) — the Automation tab from the mockups.

Phase 1 is a SCAFFOLD: the model, a sample set, and enable/disable toggles that
persist in memory, so the tab is real and clickable. The engine that actually fires
routines on a schedule (a small time/trigger loop that drives poller.apply) is a
later phase — kept out here deliberately so the tab isn't pretending to run things
it doesn't yet. No hidden truncation: toggles change the flag and nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class Automation:
    id: str
    name: str
    icon: str              # UI glyph key: "sun" | "moon" | "away" | "clock"
    subtitle: str          # e.g. "Everyday at 7:00 AM"
    scope: str = "Home"    # location label shown on the chip
    time_range: str = ""   # e.g. "7:00 - 8:00 AM"
    device_ids: List[str] = field(default_factory=list)
    enabled: bool = True

    def public_dict(self, name_of: Optional[Callable[[str], str]] = None) -> Dict[str, object]:
        names = [name_of(d) if name_of else d for d in self.device_ids]
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "subtitle": self.subtitle,
            "scope": self.scope,
            "time_range": self.time_range,
            "enabled": self.enabled,
            "device_ids": list(self.device_ids),
            "device_names": names,
            "device_count": len(self.device_ids),
        }


class AutomationStore:
    """In-memory set of automations with toggle support (no persistence in phase 1)."""

    def __init__(self, automations: List[Automation]):
        self.automations = automations
        self.by_id: Dict[str, Automation] = {a.id: a for a in automations}

    def toggle(self, automation_id: str, enabled: bool) -> Dict[str, object]:
        a = self.by_id.get(automation_id)
        if a is None:
            return {"ok": False, "error": "unknown automation"}
        a.enabled = bool(enabled)
        return {"ok": True, "id": a.id, "enabled": a.enabled}


def demo_automations() -> List[Automation]:
    """The three routines from the mockup, wired to demo device ids."""
    return [
        Automation(
            id="morning-routine", name="Morning Routine", icon="sun",
            subtitle="Everyday at 7:00 AM", scope="Home", time_range="7:00 - 8:00 AM",
            device_ids=["kitchen-lights", "kitchen-coffee", "living-lamp", "living-ac"],
        ),
        Automation(
            id="night-mode", name="Night Mode", icon="moon",
            subtitle="Everyday at 10:00 PM", scope="Home", time_range="10:00 - 11:00 PM",
            device_ids=["living-lamp", "living-tv", "bedroom-lamp", "porch-lights"],
        ),
        Automation(
            id="away-mode", name="Away Mode", icon="away",
            subtitle="When leaving home", scope="Home", time_range="",
            device_ids=["living-lamp", "living-tv", "living-ac", "kitchen-lights",
                        "office-desk", "garage-heater", "porch-lights"],
            enabled=False,
        ),
    ]
