"""The Qt binding: FreeCAD's `PySide` shim, else PySide6 (Qt 6 only)."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtWidgets
else:
    try:
        from PySide import QtCore, QtGui, QtWidgets
    except ImportError:     # outside FreeCAD: the tests, an IDE
        from PySide6 import QtCore, QtGui, QtWidgets

__all__ = ["QtCompat", "QtCore", "QtGui", "QtWidgets"]


class QtCompat:
    """What differs between Qt builds or bindings."""

    @staticmethod
    def enum_int(value: Any) -> int:
        """A Qt enum as a plain int; PySide6 enums are not IntEnum."""
        return int(value.value if isinstance(value, Enum) else value)

    @staticmethod
    def version() -> str:
        return str(QtCore.qVersion())
