"""Filters that see every event in the application."""

from __future__ import annotations

from ..qt import QtCore, QtWidgets


class ApplicationEventFilter(QtCore.QObject):
    """Installed on the whole application; subclasses define eventFilter.

    Every event in FreeCAD passes through one of these, so eventFilter
    must reject what it does not want with its cheapest test first.
    """

    def install(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
