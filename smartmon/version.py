"""Version / build info surfaced in the UI, so you can tell at a glance which commit is
running — i.e. whether a `git pull` + service restart actually took effect.

The commit short-SHA is read from git once (lazily, then cached) and changes on every push,
which is the reliable "did the new code deploy" signal; the version number is a friendlier
human label. Best-effort: if git isn't available (or this isn't a checkout), commit is None
and only the version shows.
"""
from __future__ import annotations

import os
import subprocess

from . import __version__

_commit_cache = "unset"  # sentinel so a real None (git unavailable) is cached, not re-read


def _read_commit():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (parent of smartmon/)
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        return (out.stdout or "").strip() or None
    except Exception:
        return None


def commit():
    global _commit_cache
    if _commit_cache == "unset":
        _commit_cache = _read_commit()
    return _commit_cache


def info() -> dict:
    return {"version": __version__, "commit": commit()}
