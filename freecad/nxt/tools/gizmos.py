"""Step behaviour of FreeCAD's 3D drag handles ("gizmos").

Driven by hidden preferences in Gui/Gizmos and History/Dragger. Nxt sets
fine-on-plain-drag with Ctrl for coarse once, and restores FreeCAD's
values when it is disabled or removed.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import FreeCAD as App

from ..core import settings

GIZMOS = "User parameter:BaseApp/Preferences/Gui/Gizmos"
HISTORY = "User parameter:BaseApp/History/Dragger"
ENABLED = "EnableGizmos"

#: Qt::KeyboardModifier values; FineSnapModifier toggles either way.
SHIFT = 0x02000000
CTRL = 0x04000000
ALT = 0x08000000
KEYS = {"shift": SHIFT, "ctrl": CTRL, "alt": ALT}

#: FreeCAD's value for DefaultCoarseDragBehavior.
FINE_FIRST = 1
COARSE_FIRST = 0

OURS = {"DefaultCoarseDragBehavior": FINE_FIRST, "FineSnapModifier": CTRL}

#: Addon Manager markers: DISABLED present or MANIFEST gone means Nxt
#: will not run at the next start.
DISABLED = "ADDON_DISABLED"
MANIFEST = "package.xml"

DEFAULTS: dict[str, Any] = {
    "plain": "fine",
    "key": "ctrl",
    "coarse": True,
    "step": 1.0,
    "linear": 5,
    "rotation": 5,
}


def read() -> dict[str, Any]:
    """The current settings, in Nxt's terms."""
    gizmos = App.ParamGet(GIZMOS)
    history = App.ParamGet(HISTORY)
    modifier = gizmos.GetInt("FineSnapModifier", SHIFT)
    key = next((k for k, v in KEYS.items() if v == modifier), "shift")
    first = gizmos.GetInt("DefaultCoarseDragBehavior", COARSE_FIRST)
    return {
        "plain": "fine" if first == FINE_FIRST else "coarse",
        "key": key,
        "coarse": gizmos.GetBool("EnableCoarseSnap", True),
        "step": history.GetFloat("LastTranslationIncrement", 1.0),
        "linear": gizmos.GetInt("CoarseLinearSnapMultiplier", 5),
        "rotation": gizmos.GetInt("CoarseRotationSnapMultiplier", 5),
    }


def write(values: dict[str, Any]) -> None:
    """Store settings given in Nxt's terms; missing keys are left alone."""
    gizmos = App.ParamGet(GIZMOS)
    if "plain" in values:
        gizmos.SetInt("DefaultCoarseDragBehavior",
                      FINE_FIRST if values["plain"] == "fine"
                      else COARSE_FIRST)
    if "key" in values and values["key"] in KEYS:
        gizmos.SetInt("FineSnapModifier", KEYS[values["key"]])
    if "coarse" in values:
        gizmos.SetBool("EnableCoarseSnap", bool(values["coarse"]))
    if "linear" in values:
        gizmos.SetInt("CoarseLinearSnapMultiplier",
                      max(1, int(values["linear"])))
    if "rotation" in values:
        gizmos.SetInt("CoarseRotationSnapMultiplier",
                      max(1, int(values["rotation"])))
    if "step" in values:
        App.ParamGet(HISTORY).SetFloat(
            "LastTranslationIncrement", max(0.001, float(values["step"])))


@contextlib.contextmanager
def hidden() -> Iterator[None]:
    """Open an edit without its drag handles.

    FreeCAD reads the preference only when the task is created, so it is
    switched off just for that moment.
    """
    group = App.ParamGet(GIZMOS)
    was_on = bool(group.GetBool(ENABLED, True))
    if was_on:
        group.SetBool(ENABLED, False)
    try:
        yield
    finally:
        if was_on:
            group.SetBool(ENABLED, True)


def apply_defaults_once() -> bool:
    """Set Nxt's drag defaults on the first run only. True if it did."""
    if settings.get("GizmoDefaultsApplied"):
        return False
    try:
        group = App.ParamGet(GIZMOS)
        present = set(group.GetInts())
        settings.put("GizmoOriginals", json.dumps({
            name: group.GetInt(name, 0) if name in present else None
            for name in OURS}))
        for name, value in OURS.items():
            group.SetInt(name, value)
    except Exception:
        App.Console.PrintError("Nxt: could not set the drag defaults\n")
        return False
    settings.put("GizmoDefaultsApplied", True)
    return True


def restore_freecads() -> bool:
    """Restore values Nxt replaced, unless the user changed them since."""
    if not settings.get("GizmoDefaultsApplied"):
        return False
    try:
        originals = json.loads(settings.get("GizmoOriginals") or "{}")
    except ValueError:
        originals = {}
    group = App.ParamGet(GIZMOS)
    present = set(group.GetInts())
    for name, value in OURS.items():
        if name not in present or group.GetInt(name, 0) != value:
            continue
        before = originals.get(name)
        if before is None:
            group.RemInt(name)
        else:
            group.SetInt(name, int(before))
    settings.put("GizmoOriginals", "")
    settings.put("GizmoDefaultsApplied", False)
    return True


def restore_if_leaving(root: Path) -> bool:
    """At quit: restore_freecads if Nxt will not run at the next start."""
    if (root / DISABLED).exists() or not (root / MANIFEST).exists():
        return restore_freecads()
    return False
