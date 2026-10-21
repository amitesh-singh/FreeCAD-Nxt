"""Leaving no trace in user.cfg when Nxt is removed.

Run by uninstall.py when the Addon Manager removes Nxt, and again at the
quit after, since Nxt still running may write its settings once more.
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD as App

from ..core import settings
from ..tools import gizmos

MOD = settings.GROUP.rsplit("/", 1)[0]
NAME = settings.GROUP.rsplit("/", 1)[1]


def remove_all() -> None:
    """Put back FreeCAD's values and delete Nxt's own settings."""
    gizmos.restore_freecads()
    try:
        from . import update_check
        update_check.unhush()   # the Report view's settings, if a check
    except Exception:  # noqa: BLE001 - no Qt here: nothing was hushed
        pass
    settings.removed = True
    App.ParamGet(MOD).RemGroup(NAME)


def at_quit(root: Path) -> None:
    """Clean up if Nxt is gone; only restore FreeCAD's if just disabled."""
    if not (root / gizmos.MANIFEST).exists():
        remove_all()
    elif (root / gizmos.DISABLED).exists():
        gizmos.restore_freecads()
