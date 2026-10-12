"""Finding FreeCAD's 3D views among the main window's widgets."""

from __future__ import annotations

from typing import Any

import FreeCADGui as Gui

from .qt import QtWidgets

VIEW3D_CLASS = "Gui::View3DInventor"


def mdi_area() -> Any:
    main = Gui.getMainWindow()
    return main.findChild(QtWidgets.QMdiArea) if main is not None else None


def view3d_holding(widget: Any) -> Any:
    """The 3D view window `widget` is part of, or None."""
    while widget is not None:
        try:
            if widget.metaObject().className() == VIEW3D_CLASS:
                return widget
            widget = widget.parentWidget()
        except (RuntimeError, AttributeError):
            return None
    return None


def active_viewport() -> Any:
    """The widget the active MDI window's 3D view draws into, or None.

    The active window only: with two documents open, the first visible
    3D view may belong to the other one.
    """
    area = mdi_area()
    sub = area.activeSubWindow() if area is not None else None
    holder = sub.widget() if sub is not None else None
    if holder is None or holder.metaObject().className() != VIEW3D_CLASS:
        return None
    for child in holder.findChildren(QtWidgets.QWidget):
        if "GL" in child.metaObject().className() and child.isVisible():
            return child
    return None
