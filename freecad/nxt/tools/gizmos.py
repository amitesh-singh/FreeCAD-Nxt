"""Step behaviour of FreeCAD's 3D drag handles ("gizmos").

Driven by hidden preferences in Gui/Gizmos and History/Dragger. Nxt sets
fine-on-plain-drag with Ctrl for coarse once. Every value Nxt writes here
is recorded with what it replaced, and put back when Nxt is disabled or
removed unless the user has changed it since.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
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

#: Parameter getter, setter, lister and remover for each value type.
KINDS = {
    "Int": ("GetInt", "SetInt", "GetInts", "RemInt"),
    "Bool": ("GetBool", "SetBool", "GetBools", "RemBool"),
    "Float": ("GetFloat", "SetFloat", "GetFloats", "RemFloat"),
}

#: Addon Manager markers: DISABLED present means Nxt is disabled,
#: MANIFEST gone means it was removed (app/cleanup.py).
DISABLED = "ADDON_DISABLED"
MANIFEST = "package.xml"

DEFAULTS: dict[str, Any] = {
    "plain": "fine",
    "key": "ctrl",
    "coarse": True,
    "step": 1.0,
    "linear": 5,
    "rotation": 5,
    "turn": 15.0,
}
#: Units stepped as angles.
ANGULAR = ("°", "deg")


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
        "turn": history.GetFloat("LastRotationIncrement", 15.0),
    }


def wheel_step(values: dict[str, Any], unit: str, modifiers: int) -> float:
    """A wheel notch on a field, fine or coarse as a drag handle steps.

    Lengths step by the handles' increment, angles by their rotation's,
    plain numbers by one; coarse is that times the handle's multiplier.
    The modifier key swaps plain fine and coarse, as it does on a drag.
    """
    angular = unit.strip() in ANGULAR
    fine = (float(values["turn"]) if angular
            else float(values["step"]) if unit.strip() else 1.0)
    coarse = fine * (int(values["rotation"]) if angular
                     else int(values["linear"])) \
        if values["coarse"] else fine
    held = bool(modifiers & KEYS.get(values["key"], CTRL))
    plain_fine = values["plain"] == "fine"
    return fine if plain_fine != held else coarse


def write(values: dict[str, Any]) -> None:
    """Store settings given in Nxt's terms; missing keys are left alone."""
    if "plain" in values:
        _set(GIZMOS, "Int", "DefaultCoarseDragBehavior",
             FINE_FIRST if values["plain"] == "fine" else COARSE_FIRST)
    if "key" in values and values["key"] in KEYS:
        _set(GIZMOS, "Int", "FineSnapModifier", KEYS[values["key"]])
    if "coarse" in values:
        _set(GIZMOS, "Bool", "EnableCoarseSnap", bool(values["coarse"]))
    if "linear" in values:
        _set(GIZMOS, "Int", "CoarseLinearSnapMultiplier",
             max(1, int(values["linear"])))
    if "rotation" in values:
        _set(GIZMOS, "Int", "CoarseRotationSnapMultiplier",
             max(1, int(values["rotation"])))
    if "step" in values:
        _set(HISTORY, "Float", "LastTranslationIncrement",
             max(0.001, float(values["step"])))


def _ledger() -> dict[str, list[Any]]:
    """"group|kind|name" -> [value before Nxt or None if unset, Nxt's]."""
    try:
        ledger = json.loads(settings.get("ForeignOriginals") or "{}")
    except ValueError:
        ledger = {}
    try:
        legacy = json.loads(settings.get("GizmoOriginals") or "{}")
    except ValueError:
        legacy = {}
    for name, before in legacy.items():
        if name in OURS:
            ledger.setdefault("%s|Int|%s" % (GIZMOS, name),
                              [before, OURS[name]])
    return ledger


def _set(path: str, kind: str, name: str, value: Any) -> None:
    getter, setter, lister, _remover = KINDS[kind]
    group = App.ParamGet(path)
    ledger = _ledger()
    key = "%s|%s|%s" % (path, kind, name)
    if key not in ledger:
        present = name in getattr(group, lister)()
        ledger[key] = [getattr(group, getter)(name) if present else None,
                       None]
    getattr(group, setter)(name, value)
    ledger[key][1] = value
    settings.put("ForeignOriginals", json.dumps(ledger))
    settings.put("GizmoOriginals", "")


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
        for name, value in OURS.items():
            _set(GIZMOS, "Int", name, value)
    except Exception:
        App.Console.PrintError("Nxt: could not set the drag defaults\n")
        return False
    settings.put("GizmoDefaultsApplied", True)
    return True


def restore_freecads() -> bool:
    """Put back every value Nxt wrote, unless the user changed it since."""
    ledger = _ledger()
    if not ledger and not settings.get("GizmoDefaultsApplied"):
        return False
    for key, (before, ours) in ledger.items():
        path, kind, name = key.split("|")
        getter, setter, lister, remover = KINDS[kind]
        group = App.ParamGet(path)
        if name not in getattr(group, lister)() \
                or getattr(group, getter)(name) != ours:
            continue
        if before is None:
            getattr(group, remover)(name)
        else:
            getattr(group, setter)(name, before)
    settings.put("ForeignOriginals", "")
    settings.put("GizmoOriginals", "")
    settings.put("GizmoDefaultsApplied", False)
    return True
