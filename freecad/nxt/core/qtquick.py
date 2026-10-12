"""QtQuick, imported only when a QML surface is built.

From PySide6 directly: FreeCAD's `PySide` shim does not carry these modules.
"""

from __future__ import annotations

import os
from types import ModuleType

#: Share the Coin3D viewport's graphics API rather than let RHI pick Vulkan.
SCENEGRAPH_BACKEND = "opengl"


def use_shared_graphics_api() -> None:
    """Ask Qt for the viewport's graphics API; call before any QML exists.

    Process-wide, so deferred to first QtQuick use; respects an existing value.
    """
    os.environ.setdefault("QSG_RHI_BACKEND", SCENEGRAPH_BACKEND)


def modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    """(QtQml, QtQuick, QtQuickWidgets), or ImportError at the point of use."""
    from PySide6 import QtQml, QtQuick, QtQuickWidgets
    return QtQml, QtQuick, QtQuickWidgets


def available() -> bool:
    try:
        modules()
    except ImportError:
        return False
    return True
