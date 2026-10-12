"""The addon's assets, located through importlib.resources.

Resolved from the package, not `__file__`, so any install layout works.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_ROOT = files(__name__)

#: Command and addon icons, registered with FreeCAD's icon path.
ICONS = Path(str(_ROOT / "icons"))
#: The logo; FreeCAD's Preferences finds a copy, preferences-freecad-nxt.svg.
LOGO = ICONS / "FreeCAD-Nxt.svg"

#: QML: the panel's and inspector's root files, and the `Nxt` module.
QML = Path(str(_ROOT / "qml"))

#: Context menu definitions; `default.toml` is Nxt's own.
MENUS = Path(str(_ROOT / "menus"))

#: Compiled translations, Nxt_<locale>.qm, for FreeCAD's language path.
TRANSLATIONS = Path(str(_ROOT / "translations"))


def qml(name: str) -> Path:
    """A root QML file, such as 'NxtTree.qml'."""
    return QML / name
